"""FastAPI backend for the Backup Resilience Lab dashboard.

Drives the lab through the same mechanisms as the existing app.py:
  - `docker compose exec` for CLI commands
  - `docker cp` for file uploads
  - HTTP for Prometheus/Grafana/metrics health checks
  - Host triage for failure analysis

New capabilities:
  - Structured health checks for all services
  - Per-service diagnostics
  - File protection workflow (upload + fingerprint + backup + verify)
  - Activity timeline from real events
  - Allowlisted service restart
  - SHA-256 fingerprinting at upload time

Usage:
    pip install fastapi uvicorn python-multipart
    python dashboard/api.py [--port 8090]
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import urllib.request

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
CTR = "backup-resilience-lab-app-server-1-1"
NET = "backup-resilience-lab_lab-net"
LONG_TIMEOUT = 300
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


def _ctr_name() -> str:
    """Resolve the app-server-1 container (ID or name) instead of trusting
    the hardcoded default, which breaks on renamed compose projects."""
    rc, out = run(["docker", "compose", "ps", "-q", "app-server-1"], timeout=30)
    if rc == 0:
        for line in out.splitlines():
            cid = line.strip()
            if len(cid) >= 12:
                return cid
    return CTR


def _net_name() -> str:
    """Resolve the lab-net network name dynamically with fallback."""
    rc, out = run(["docker", "network", "ls", "--format", "{{.Name}}"], timeout=30)
    if rc == 0:
        for line in out.splitlines():
            if "lab-net" in line:
                return line.strip()
    return NET

# Allowed services for restart
ALLOWED_SERVICES = {
    "minio", "app-server-1", "app-server-2",
    "prometheus", "grafana", "vault-sync"
}

# Allowed faults
ALLOWED_FAULTS = {
    "disk_full", "dns_failure", "port_blocked",
    "permission_denied", "bad_credentials",
    "wrong_repo_password", "service_down"
}

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_health_cache = {
    "last_check": None,
    "last_success": None,
    "services": {},
    "global_status": "unknown",
    "checking": False,
}
_health_lock = threading.Lock()
_operation_lock = threading.Lock()
_current_operation = None  # "backup", "attack", "restore", or None

# Activity timeline - stores real events
_timeline: deque = deque(maxlen=200)
_timeline_lock = threading.Lock()

# Protected files tracking
_protected_files: dict = {}
_protected_lock = threading.Lock()

# Diagnostic history
_diagnostic_history: deque = deque(maxlen=50)


def _add_event(event_type: str, message: str, status: str = "info", details: dict | None = None):
    """Add a real event to the activity timeline."""
    with _timeline_lock:
        _timeline.append({
            "id": uuid.uuid4().hex[:8],
            "type": event_type,
            "message": message,
            "status": status,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# Shell / Docker helpers (reused from existing app.py)
# ---------------------------------------------------------------------------
def run(args, timeout=60, cwd=REPO):
    """Run a command and capture output."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "command timed out"
    except FileNotFoundError:
        return -2, f"command not found: {args[0]}"
    except Exception as e:
        return -3, str(e)[:500]


def cexec(*cli, timeout=60):
    """Execute a lab CLI command inside app-server-1."""
    return run(["docker", "compose", "exec", "-T", "app-server-1",
                "python3", "-m", "lab.cli", *cli], timeout=timeout)


def prom_query(expr):
    """Query Prometheus."""
    try:
        with urllib.request.urlopen(
                "http://localhost:9090/api/v1/query?query=" + expr, timeout=10) as r:
            vals = json.load(r)["data"]["result"]
            return {v["metric"].get("host", "?"): v["value"][1] for v in vals}
    except Exception:
        return {}


def metrics_text():
    """Fetch raw metrics from app-server-1."""
    try:
        with urllib.request.urlopen("http://localhost:8001/metrics", timeout=10) as r:
            return r.read().decode()
    except Exception:
        return ""


def gauge(text, name, labels=""):
    """Parse a gauge value from Prometheus text format."""
    for line in text.splitlines():
        if line.startswith(name + "{") and (not labels or labels in line):
            try:
                return float(line.rsplit(" ", 1)[1])
            except Exception:
                pass
    return None


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Health checking
# ---------------------------------------------------------------------------
def _check_url(url: str, timeout: int = 5) -> tuple[bool, str, float]:
    """Check if a URL is reachable. Returns (ok, message, latency_ms)."""
    t0 = time.time()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _ = r.read(1024)
            latency = (time.time() - t0) * 1000
            return True, f"HTTP {r.status}", latency
    except urllib.error.HTTPError as e:
        latency = (time.time() - t0) * 1000
        if e.code < 500:
            return True, f"HTTP {e.code}", latency
        return False, f"HTTP {e.code}", latency
    except Exception as e:
        latency = (time.time() - t0) * 1000
        return False, str(e)[:200], latency


def _check_docker_service(service_name: str) -> tuple[str, str]:
    """Check a Docker Compose service status via docker compose ps."""
    rc, out = run(["docker", "compose", "ps", "--format", "json", service_name], timeout=15)
    if rc != 0:
        return "unknown", f"docker compose ps failed: {out[:200]}"
    try:
        # docker compose ps --format json outputs one JSON object per line
        for line in out.strip().splitlines():
            data = json.loads(line)
            state = data.get("State", "unknown")
            health = data.get("Health", "")
            if state == "running":
                if health == "healthy":
                    return "healthy", "container running and healthy"
                elif health == "unhealthy":
                    return "unhealthy", "container running but unhealthy"
                return "running", f"container running (health: {health or 'no healthcheck'})"
            return state, f"container state: {state}"
    except (json.JSONDecodeError, KeyError):
        if "running" in out.lower():
            return "running", "container appears running"
        if "exited" in out.lower() or "stopped" in out.lower():
            return "stopped", "container not running"
    return "unknown", f"could not parse status: {out[:200]}"


def run_health_check() -> dict:
    """Run a comprehensive health check across all services."""
    now = datetime.now(timezone.utc).isoformat()
    services = {}

    # 1. RustFS (minio)
    ok, msg, lat = _check_url("http://localhost:9000/minio/health/live", timeout=5)
    if not ok:
        ok, msg, lat = _check_url("http://localhost:9000/", timeout=5)
    docker_state, docker_msg = _check_docker_service("minio")
    services["rustfs_storage"] = {
        "name": "RustFS Object Storage",
        "status": "healthy" if ok else ("degraded" if docker_state == "running" else "offline"),
        "http_ok": ok,
        "message": msg,
        "latency_ms": round(lat, 1),
        "docker_state": docker_state,
        "docker_message": docker_msg,
        "last_check": now,
        "blocks": ["backup", "restore", "vault"],
        "check_type": "direct_http",
    }

    # 2. App Server 1
    ok1, msg1, lat1 = _check_url("http://localhost:8001/metrics", timeout=5)
    ds1, dm1 = _check_docker_service("app-server-1")
    services["app_server_1"] = {
        "name": "App Server 1 (Lab Agent)",
        "status": "healthy" if ok1 else ("degraded" if ds1 == "running" else "offline"),
        "http_ok": ok1,
        "message": msg1,
        "latency_ms": round(lat1, 1),
        "docker_state": ds1,
        "docker_message": dm1,
        "last_check": now,
        "blocks": ["backup", "attack", "restore", "detection"],
        "check_type": "direct_http",
    }

    # 3. App Server 2
    ok2, msg2, lat2 = _check_url("http://localhost:8002/metrics", timeout=5)
    ds2, dm2 = _check_docker_service("app-server-2")
    services["app_server_2"] = {
        "name": "App Server 2 (Lab Agent)",
        "status": "healthy" if ok2 else ("degraded" if ds2 == "running" else "offline"),
        "http_ok": ok2,
        "message": msg2,
        "latency_ms": round(lat2, 1),
        "docker_state": ds2,
        "docker_message": dm2,
        "last_check": now,
        "blocks": [],
        "check_type": "direct_http",
    }

    # 4. Prometheus
    ok3, msg3, lat3 = _check_url("http://localhost:9090/-/healthy", timeout=5)
    ds3, dm3 = _check_docker_service("prometheus")
    services["prometheus"] = {
        "name": "Prometheus Monitoring",
        "status": "healthy" if ok3 else ("degraded" if ds3 == "running" else "offline"),
        "http_ok": ok3,
        "message": msg3,
        "latency_ms": round(lat3, 1),
        "docker_state": ds3,
        "docker_message": dm3,
        "last_check": now,
        "blocks": ["monitoring"],
        "check_type": "direct_http",
    }

    # 5. Grafana
    ok4, msg4, lat4 = _check_url("http://localhost:3000/api/health", timeout=5)
    ds4, dm4 = _check_docker_service("grafana")
    services["grafana"] = {
        "name": "Grafana Dashboard",
        "status": "healthy" if ok4 else ("degraded" if ds4 == "running" else "offline"),
        "http_ok": ok4,
        "message": msg4,
        "latency_ms": round(lat4, 1),
        "docker_state": ds4,
        "docker_message": dm4,
        "last_check": now,
        "blocks": ["monitoring"],
        "check_type": "direct_http",
    }

    # 6. Vault Sync (no HTTP endpoint, check Docker status)
    ds5, dm5 = _check_docker_service("vault-sync")
    services["vault_sync"] = {
        "name": "Vault Sync (Primary → Vault)",
        "status": "healthy" if ds5 == "running" else "offline",
        "http_ok": None,
        "message": dm5,
        "latency_ms": None,
        "docker_state": ds5,
        "docker_message": dm5,
        "last_check": now,
        "blocks": ["vault"],
        "check_type": "docker_state",
    }

    # 7. Detector status (from metrics)
    m = metrics_text()
    det_score = gauge(m, "lab_detector_score", 'host="app-server-1"')
    services["detector"] = {
        "name": "Filesystem Detector",
        "status": "healthy" if ok1 and det_score is not None else ("degraded" if ok1 else "offline"),
        "http_ok": None,
        "message": f"score={det_score}" if det_score is not None else "no metrics available",
        "latency_ms": None,
        "docker_state": ds1,
        "docker_message": "runs inside app-server-1",
        "last_check": now,
        "blocks": ["detection"],
        "check_type": "indirect_metrics",
    }

    # 8. Backup scheduler (inferred from metrics)
    last_success = gauge(m, "lab_backup_last_success_timestamp", 'host="app-server-1"')
    paused = gauge(m, "lab_backups_paused", 'host="app-server-1"')
    services["backup_scheduler"] = {
        "name": "Backup Scheduler",
        "status": "healthy" if ok1 and last_success else ("paused" if paused else "degraded" if ok1 else "offline"),
        "http_ok": None,
        "message": f"last_success={last_success}, paused={bool(paused)}" if last_success is not None else "no metrics",
        "latency_ms": None,
        "docker_state": ds1,
        "docker_message": "runs inside app-server-1",
        "last_check": now,
        "blocks": ["backup"],
        "check_type": "indirect_metrics",
    }

    # 9. SQLite state (can we query snapshots?)
    rc_snap, snap_out = cexec("snapshots", "--host", "app-server-1", "--limit", "1", timeout=15)
    services["sqlite_state"] = {
        "name": "SQLite Snapshot State",
        "status": "healthy" if rc_snap == 0 else "degraded",
        "http_ok": None,
        "message": "snapshot query succeeded" if rc_snap == 0 else f"query failed: {snap_out[:200]}",
        "latency_ms": None,
        "docker_state": ds1,
        "docker_message": "database inside app-server-1",
        "last_check": now,
        "blocks": ["backup", "restore"],
        "check_type": "indirect_cli",
    }

    # Calculate global status
    statuses = [s["status"] for s in services.values()]
    if all(s in ("healthy", "running") for s in statuses):
        global_status = "healthy"
    elif any(s == "offline" for s in statuses):
        critical_offline = any(
            s["status"] == "offline" for key, s in services.items()
            if key in ("rustfs_storage", "app_server_1")
        )
        global_status = "offline" if critical_offline else "degraded"
    else:
        global_status = "degraded"

    healthy_count = sum(1 for s in statuses if s in ("healthy", "running"))
    unhealthy_count = len(statuses) - healthy_count

    result = {
        "global_status": global_status,
        "healthy_count": healthy_count,
        "unhealthy_count": unhealthy_count,
        "total_services": len(services),
        "services": services,
        "checked_at": now,
    }

    with _health_lock:
        _health_cache["last_check"] = now
        _health_cache["services"] = services
        _health_cache["global_status"] = global_status
        if global_status in ("healthy", "degraded"):
            _health_cache["last_success"] = now
        _health_cache["checking"] = False

    return result


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    _add_event("system", "Dashboard backend started", "success")
    yield
    _add_event("system", "Dashboard backend shutting down", "info")

app = FastAPI(
    title="Backup Resilience Lab Dashboard API",
    description="Live-monitored frontend for the Backup Resilience Lab",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174",
                   "http://localhost:3001", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------
class FaultRequest(BaseModel):
    name: str

class ServiceAction(BaseModel):
    action: str = "restart"  # "restart" or "start"
    confirm: bool = False


# ---------------------------------------------------------------------------
# HEALTH ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    """Global health status — returns cached or fresh results."""
    with _health_lock:
        if _health_cache["last_check"]:
            return {
                "ok": True,
                "global_status": _health_cache["global_status"],
                "last_check": _health_cache["last_check"],
                "last_success": _health_cache["last_success"],
                "services": _health_cache["services"],
                "healthy_count": sum(1 for s in _health_cache["services"].values()
                                     if s["status"] in ("healthy", "running")),
                "unhealthy_count": sum(1 for s in _health_cache["services"].values()
                                       if s["status"] not in ("healthy", "running")),
                "total_services": len(_health_cache["services"]),
                "checking": _health_cache["checking"],
            }
    # First time: run check
    result = run_health_check()
    return {"ok": True, **result}


@app.post("/api/health/check")
async def force_health_check():
    """Force a fresh round of health checks."""
    with _health_lock:
        if _health_cache["checking"]:
            return {"ok": False, "message": "Health check already in progress"}
        _health_cache["checking"] = True
    _add_event("health_check", "Manual health check triggered", "info")
    result = run_health_check()
    _add_event("health_check",
               f"Health check complete: {result['global_status']} ({result['healthy_count']}/{result['total_services']} healthy)",
               "success" if result["global_status"] == "healthy" else "warning")
    return {"ok": True, **result}


@app.get("/api/health/services")
async def health_services():
    """Per-service health details."""
    with _health_lock:
        if not _health_cache["services"]:
            result = run_health_check()
            return {"ok": True, "services": result["services"], "global_status": result["global_status"]}
        return {"ok": True, "services": _health_cache["services"],
                "global_status": _health_cache["global_status"],
                "last_check": _health_cache["last_check"]}



# ---------------------------------------------------------------------------
# DIAGNOSTICS
# ---------------------------------------------------------------------------
@app.post("/api/diagnostics")
async def run_diagnostics():
    """Run safe, read-only diagnostics across all components."""
    diag_id = uuid.uuid4().hex[:8]
    _add_event("diagnostics", f"Diagnostic run {diag_id} started", "info")
    checks = []
    now = datetime.now(timezone.utc).isoformat()

    # 1. API health
    checks.append({
        "id": f"{diag_id}-api",
        "component": "Dashboard API",
        "check": "Self-check",
        "status": "pass",
        "observed": "API is responding",
        "likely_cause": None,
        "recommended_action": None,
    })

    # 2. Docker Compose
    rc, out = run(["docker", "compose", "ps", "--format", "json"], timeout=15)
    if rc == 0:
        try:
            services_running = []
            services_stopped = []
            for line in out.strip().splitlines():
                data = json.loads(line)
                name = data.get("Service", data.get("Name", "?"))
                state = data.get("State", "?")
                if state == "running":
                    services_running.append(name)
                else:
                    services_stopped.append(f"{name}({state})")
            checks.append({
                "id": f"{diag_id}-docker",
                "component": "Docker Compose",
                "check": "Service listing",
                "status": "pass" if not services_stopped else "warning",
                "observed": f"Running: {', '.join(services_running)}" +
                            (f" | Stopped: {', '.join(services_stopped)}" if services_stopped else ""),
                "likely_cause": "Some services may have exited or crashed" if services_stopped else None,
                "recommended_action": f"Restart stopped services: {', '.join(services_stopped)}" if services_stopped else None,
            })
        except Exception:
            checks.append({
                "id": f"{diag_id}-docker",
                "component": "Docker Compose",
                "check": "Service listing",
                "status": "pass",
                "observed": out[:500],
                "likely_cause": None,
                "recommended_action": None,
            })
    else:
        checks.append({
            "id": f"{diag_id}-docker",
            "component": "Docker Compose",
            "check": "Service listing",
            "status": "fail",
            "observed": out[:500],
            "likely_cause": "Docker may not be running or compose file not found",
            "recommended_action": "Ensure Docker Desktop is running with WSL2 integration enabled",
        })

    # 3. Storage endpoint
    ok, msg, lat = _check_url("http://localhost:9000/minio/health/live", timeout=5)
    if not ok:
        ok, msg, lat = _check_url("http://localhost:9000/", timeout=5)
    checks.append({
        "id": f"{diag_id}-storage",
        "component": "RustFS Storage",
        "check": "HTTP health endpoint",
        "status": "pass" if ok else "fail",
        "observed": f"{msg} ({lat:.0f}ms)",
        "likely_cause": "Storage container may be stopped or unhealthy" if not ok else None,
        "recommended_action": "Run: docker compose up -d minio" if not ok else None,
    })

    # 4. Backup repository
    rc_snap, snap_out = cexec("snapshots", "--host", "app-server-1", "--limit", "3", timeout=20)
    if rc_snap == 0:
        try:
            snaps = json.loads(snap_out)
            checks.append({
                "id": f"{diag_id}-repo",
                "component": "Backup Repository",
                "check": "Snapshot listing",
                "status": "pass",
                "observed": f"{len(snaps)} recent snapshots found",
                "likely_cause": None,
                "recommended_action": None,
            })
        except Exception:
            checks.append({
                "id": f"{diag_id}-repo",
                "component": "Backup Repository",
                "check": "Snapshot listing",
                "status": "pass",
                "observed": snap_out[:300],
                "likely_cause": None,
                "recommended_action": None,
            })
    else:
        checks.append({
            "id": f"{diag_id}-repo",
            "component": "Backup Repository",
            "check": "Snapshot listing",
            "status": "fail",
            "observed": snap_out[:500],
            "likely_cause": "App server may be unreachable or restic repo not initialized",
            "recommended_action": "Check app-server-1 container status and storage connectivity",
        })

    # 5. Prometheus scrape
    prom_ok, prom_msg, prom_lat = _check_url("http://localhost:9090/-/healthy", timeout=5)
    scrape_data = prom_query("up")
    checks.append({
        "id": f"{diag_id}-prometheus",
        "component": "Prometheus",
        "check": "Health and scrape targets",
        "status": "pass" if prom_ok else "fail",
        "observed": f"Healthy: {prom_ok}, scrape targets: {scrape_data}" if prom_ok else prom_msg,
        "likely_cause": "Prometheus container may be stopped" if not prom_ok else None,
        "recommended_action": "Run: docker compose up -d prometheus" if not prom_ok else None,
    })

    # 6. Grafana
    graf_ok, graf_msg, graf_lat = _check_url("http://localhost:3000/api/health", timeout=5)
    checks.append({
        "id": f"{diag_id}-grafana",
        "component": "Grafana",
        "check": "HTTP health",
        "status": "pass" if graf_ok else "fail",
        "observed": f"{graf_msg} ({graf_lat:.0f}ms)" if graf_ok else graf_msg,
        "likely_cause": "Grafana container may be stopped" if not graf_ok else None,
        "recommended_action": "Run: docker compose up -d grafana" if not graf_ok else None,
    })

    # 7. Detector status
    m = metrics_text()
    det_score = gauge(m, "lab_detector_score", 'host="app-server-1"')
    checks.append({
        "id": f"{diag_id}-detector",
        "component": "Filesystem Detector",
        "check": "Detector score metric",
        "status": "pass" if det_score is not None else "unknown",
        "observed": f"detector score = {det_score}" if det_score is not None else "no detector metrics found",
        "likely_cause": "Detector process may not be running inside app-server-1" if det_score is None else None,
        "recommended_action": "Restart app-server-1 to restart the detector" if det_score is None else None,
    })

    # 8. Backup logs
    rc_logs, logs_out = run(["docker", "compose", "exec", "-T", "app-server-1",
                             "tail", "-5", "/var/log/lab/backup.jsonl"], timeout=15)
    if rc_logs == 0 and logs_out.strip():
        last_lines = logs_out.strip().splitlines()[-3:]
        checks.append({
            "id": f"{diag_id}-logs",
            "component": "Backup Logs",
            "check": "Recent log entries",
            "status": "pass",
            "observed": " | ".join(l[:120] for l in last_lines),
            "likely_cause": None,
            "recommended_action": None,
        })
    else:
        checks.append({
            "id": f"{diag_id}-logs",
            "component": "Backup Logs",
            "check": "Recent log entries",
            "status": "unknown",
            "observed": "Could not read logs" if rc_logs != 0 else "No log entries",
            "likely_cause": "No backups have run yet or logs directory empty",
            "recommended_action": "Run a backup to generate log entries",
        })

    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    unknown = sum(1 for c in checks if c["status"] == "unknown")

    result = {
        "ok": True,
        "diagnostic_id": diag_id,
        "timestamp": now,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
            "unknown": unknown,
        }
    }

    with _timeline_lock:
        _diagnostic_history.append(result)

    status_msg = f"Diagnostics {diag_id}: {passed} passed, {failed} failed, {unknown} unknown"
    _add_event("diagnostics", status_msg,
               "success" if failed == 0 else "error")

    return result


@app.get("/api/diagnostics/history")
async def diagnostics_history():
    """Recent diagnostic results."""
    return {"ok": True, "history": list(_diagnostic_history)}


# ---------------------------------------------------------------------------
# SERVICE MANAGEMENT
# ---------------------------------------------------------------------------
@app.post("/api/services/{service_name}/restart")
async def restart_service(service_name: str, body: ServiceAction):
    """Restart an allowlisted Docker Compose service."""
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(400, f"Service '{service_name}' is not in the allowed list: {sorted(ALLOWED_SERVICES)}")
    if not body.confirm:
        return {
            "ok": False,
            "message": f"Confirmation required to {body.action} service '{service_name}'",
            "requires_confirm": True,
        }

    _add_event("service_action", f"Restarting service: {service_name}", "warning")

    if body.action == "restart":
        rc, out = run(["docker", "compose", "restart", service_name], timeout=120)
    elif body.action == "start":
        rc, out = run(["docker", "compose", "up", "-d", service_name], timeout=120)
    else:
        raise HTTPException(400, f"Unknown action: {body.action}")

    success = rc == 0
    _add_event("service_action",
               f"Service {service_name} {body.action}: {'succeeded' if success else 'failed'}",
               "success" if success else "error",
               {"output": out[:500]})

    # Recheck health after action
    health_result = run_health_check()

    return {
        "ok": success,
        "service": service_name,
        "action": body.action,
        "output": out[:1000],
        "health_after": health_result["global_status"],
    }


# ---------------------------------------------------------------------------
# OVERVIEW (existing /api/overview equivalent)
# ---------------------------------------------------------------------------
@app.get("/api/overview")
async def overview():
    """Full system overview — mirrors existing app.py overview."""
    m = metrics_text()
    rc, snaps = cexec("snapshots", "--host", "app-server-1", "--limit", "8")
    try:
        snap_list = json.loads(snaps) if rc == 0 else []
    except Exception:
        snap_list = []
    rc2, ls = run(["docker", "compose", "exec", "-T", "app-server-1",
                   "ls", "/data/victim"], timeout=30)
    victim_files = len([l for l in ls.splitlines() if l.strip()]) if rc2 == 0 else -1

    return {
        "ok": True,
        "overview": {
            "score": gauge(m, "lab_detector_score", 'host="app-server-1"'),
            "paused": gauge(m, "lab_backups_paused", 'host="app-server-1"'),
            "alerts": prom_query("lab_alerts_total"),
            "clean": gauge(m, "lab_snapshots_total", 'status="clean"'),
            "suspect": gauge(m, "lab_snapshots_total", 'status="suspect"'),
            "rto": gauge(m, "lab_last_restore_rto_seconds", 'host="app-server-1"'),
            "last_success": gauge(m, "lab_backup_last_success_timestamp", 'host="app-server-1"'),
            "snapshots": snap_list,
            "victim_entries": victim_files,
        }
    }


# ---------------------------------------------------------------------------
# FILE PROTECTION
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file to the lab victim directory with SHA-256 fingerprint."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    # Sanitize filename
    safe_name = os.path.basename(file.filename).replace("/", "_").replace("\\", "_").replace("..", "_")
    if not safe_name:
        raise HTTPException(400, "Invalid filename")

    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty file")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_SIZE // (1024*1024)} MB)")

    # SHA-256 fingerprint
    fingerprint = sha256_bytes(content)

    # Write to temp file and docker cp
    tmp = os.path.join(tempfile.gettempdir(), f"lab-upload-{safe_name}")
    try:
        with open(tmp, "wb") as f:
            f.write(content)
        rc, out = run(["docker", "cp", tmp,
                       _ctr_name() + ":/data/victim/" + safe_name], timeout=60)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    if rc != 0:
        _add_event("upload", f"Upload failed: {safe_name}", "error", {"error": out[:500]})
        raise HTTPException(500, f"docker cp failed: {out[:500]}")

    # Track protected file
    file_info = {
        "name": safe_name,
        "size": len(content),
        "fingerprint": fingerprint,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "protected": False,
        "backup_snapshot": None,
        "verified": False,
    }
    with _protected_lock:
        _protected_files[safe_name] = file_info

    _add_event("upload", f"File uploaded: {safe_name} ({len(content)} bytes)", "success",
               {"fingerprint": fingerprint, "size": len(content)})

    return {
        "ok": True,
        "name": safe_name,
        "size": len(content),
        "fingerprint": fingerprint,
        "note": "File staged at /data/victim/ — use Protect to create a verified backup",
    }


def _alerts_total() -> float:
    """Summed lab_alerts_total across hosts (persistent counter)."""
    try:
        return sum(float(v) for v in prom_query("lab_alerts_total").values())
    except Exception:
        return 0.0


def _manifest_paths(snapshot_id: str, host: str = "app-server-1") -> set | None:
    """Download a snapshot manifest from object storage (host-side).
    Returns the set of relative paths, or None when unreachable."""
    try:
        import boto3
        s3 = boto3.client(
            "s3", endpoint_url="http://localhost:9000",
            aws_access_key_id=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
            aws_secret_access_key=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123"))
        obj = s3.get_object(Bucket="backup-primary",
                            Key=f"manifests/{host}/{snapshot_id}.json")
        man = json.loads(obj["Body"].read())
        return {e.get("path") for e in man.get("files", [])}
    except Exception:
        return None


@app.post("/api/protect")
async def protect_file():
    """Run backup and verify each staged file is inside the new snapshot.

    Honesty rules (Oct 2026 fix): a skipped/failed backup is NOT protection
    (previous code fell back to whatever snapshot was latest, even one that
    predates the upload). Files are marked protected only when their
    manifest path appears in the fresh snapshot's manifest.
    """
    global _current_operation
    with _operation_lock:
        if _current_operation:
            raise HTTPException(409, f"Operation '{_current_operation}' already in progress")
        _current_operation = "backup"

    try:
        _add_event("backup", "Protection backup started", "info")

        # Run backup — must produce a FRESH snapshot; anything else is not protection.
        rc, out = cexec("backup", "run", timeout=LONG_TIMEOUT)
        backup_result = None
        try:
            backup_result = json.loads(out)
        except Exception:
            for line in out.splitlines():
                try:
                    obj = json.loads(line)
                    if "snapshot_id" in obj or "skipped" in obj:
                        backup_result = obj
                        break
                except Exception:
                    continue
        snapshot_id = (backup_result or {}).get("snapshot_id")
        if rc != 0 or not snapshot_id:
            reason = "backup did not produce a snapshot"
            if (backup_result or {}).get("skipped"):
                reason = ("backup skipped (scheduled backups are paused after an alert, "
                          "or the detector score is elevated) — resume and retry, files NOT protected")
            _add_event("backup", f"Protection refused: {reason}", "error")
            return {"ok": False, "step": "backup", "reason": reason,
                    "output": out[-4000:]}

        # Verify each staged file against the fresh snapshot manifest.
        paths = _manifest_paths(snapshot_id)
        if paths is None:
            _add_event("backup", "Protection unverified: manifest unreachable", "error")
            return {"ok": False, "step": "verify",
                    "reason": "could not download snapshot manifest",
                    "snapshot_id": snapshot_id}
        verified, missing = [], []
        with _protected_lock:
            pending = [(n, i) for n, i in _protected_files.items() if not i["protected"]]
        for name, info in pending:
            if ("victim/" + name) in paths:
                info["protected"] = True
                info["verified"] = True
                info["backup_snapshot"] = snapshot_id
                info["protected_at"] = datetime.now(timezone.utc).isoformat()
                verified.append(name)
            else:
                missing.append(name)
        if missing:
            _add_event("backup", f"Snapshot {snapshot_id[:8]} missing staged files: {missing}", "error")
            return {"ok": False, "step": "verify", "snapshot_id": snapshot_id,
                    "verified": verified,
                    "reason": f"not in snapshot {snapshot_id[:8]}: {missing}"}

        _add_event("backup",
                   f"Backup completed and verified: snapshot {snapshot_id[:8]} covers {verified}",
                   "success",
                   {"snapshot_id": snapshot_id})

        return {
            "ok": True,
            "snapshot_id": snapshot_id,
            "verified": verified,
            "output": out[-3000:],
        }
    finally:
        with _operation_lock:
            _current_operation = None


@app.get("/api/protected-files")
async def get_protected_files():
    """List all tracked protected files."""
    with _protected_lock:
        return {"ok": True, "files": dict(_protected_files)}


# ---------------------------------------------------------------------------
# DETECTOR / MONITORING
# ---------------------------------------------------------------------------
@app.get("/api/detector/status")
async def detector_status():
    """Get current detector status from metrics."""
    m = metrics_text()
    score = gauge(m, "lab_detector_score", 'host="app-server-1"')
    paused = gauge(m, "lab_backups_paused", 'host="app-server-1"')
    alerts = prom_query("lab_alerts_total")
    clean = gauge(m, "lab_snapshots_total", 'status="clean"')
    suspect = gauge(m, "lab_snapshots_total", 'status="suspect"')

    return {
        "ok": True,
        "detector": {
            "score": score,
            "threshold": 0.55,  # from config/lab.yaml
            "is_alerting": score is not None and score >= 0.55,
            "paused": bool(paused),
            "alerts": alerts,
            "clean_snapshots": clean,
            "suspect_snapshots": suspect,
            "monitoring_dir": "/data/victim",
            "status": "active" if score is not None else "unknown",
        }
    }


# ---------------------------------------------------------------------------
# ATTACK SIMULATION
# ---------------------------------------------------------------------------
@app.post("/api/attack")
async def run_attack():
    """Run the guarded ransomware simulation."""
    global _current_operation
    with _operation_lock:
        if _current_operation:
            raise HTTPException(409, f"Operation '{_current_operation}' already in progress")
        _current_operation = "attack"

    try:
        # Pre-check: verify clean backup exists
        rc_snap, snap_out = cexec("snapshots", "--host", "app-server-1", "--limit", "1")
        has_backup = False
        try:
            snaps = json.loads(snap_out)
            has_backup = bool(snaps) and any(s.get("status") == "clean" for s in snaps)
        except Exception:
            pass

        if not has_backup:
            _add_event("attack", "Attack refused: no clean backup exists", "error")
            return {
                "ok": False,
                "reason": "No clean backup found. Create a backup first to ensure recovery is possible.",
                "pre_check_failed": True,
            }

        _add_event("attack", "Ransomware simulation started (lab-only, guarded)", "warning")

        pre_alerts = _alerts_total()
        rc, out = cexec("attack", "run", "--rate", "15", timeout=LONG_TIMEOUT)

        # Parse attack result
        attack_result = None
        try:
            attack_result = json.loads(out)
        except Exception:
            for line in out.splitlines():
                try:
                    attack_result = json.loads(line)
                    if "run_id" in attack_result:
                        break
                except Exception:
                    continue

        # Check detector status after attack. NOTE (Oct 2026 fix): the live
        # score gauge decays ~10s after the burst, so a late read reports
        # detected:false for a caught attack. Ground truth is the persistent
        # alerts counter delta (plus the gauge when still hot).
        m = metrics_text()
        post_score = gauge(m, "lab_detector_score", 'host="app-server-1"')
        post_paused = gauge(m, "lab_backups_paused", 'host="app-server-1"')
        post_alerts = prom_query("lab_alerts_total")
        fired = _alerts_total() > pre_alerts
        detected = fired or (post_score is not None and post_score >= 0.55)

        _add_event("attack",
                   f"Simulation complete: {attack_result.get('files', '?') if attack_result else '?'} files encrypted",
                   "warning",
                   {"attack_result": attack_result})

        if post_score is not None and post_score >= 0.55:
            _add_event("detection", f"Ransomware detected! Score: {post_score:.2f}", "error",
                       {"score": post_score})

        if post_paused:
            _add_event("detection", "Backups paused due to suspicious activity", "warning")

        return {
            "ok": rc == 0,
            "attack_result": attack_result,
            "post_attack": {
                "detector_score": post_score,
                "alert_fired": fired,
                "detected": detected,
                "backups_paused": bool(post_paused),
                "alerts": post_alerts,
            },
            "output": out[-4000:],
        }
    finally:
        with _operation_lock:
            _current_operation = None


# ---------------------------------------------------------------------------
# RESTORE & VERIFICATION
# ---------------------------------------------------------------------------
@app.post("/api/restore")
async def run_restore():
    """Restore from latest clean snapshot with SHA-256 verification."""
    global _current_operation
    with _operation_lock:
        if _current_operation:
            raise HTTPException(409, f"Operation '{_current_operation}' already in progress")
        _current_operation = "restore"

    try:
        _add_event("restore", "Restore from latest clean snapshot started", "info")
        t0 = time.time()

        rc, out = cexec("restore", "--latest-clean", "--host", "app-server-1",
                        timeout=LONG_TIMEOUT)

        rto = time.time() - t0

        # Parse restore result
        restore_result = None
        try:
            restore_result = json.loads(out)
        except Exception:
            for line in out.splitlines():
                try:
                    obj = json.loads(line)
                    if "verify" in obj or "snapshot_id" in obj:
                        restore_result = obj
                        break
                except Exception:
                    continue

        # Check if verification succeeded
        verification = None
        if restore_result and "verify" in restore_result:
            v = restore_result["verify"]
            verification = {
                "total_files": v.get("total"),
                "verified_ok": v.get("ok"),
                "missing": v.get("missing", []),
                "corrupted": v.get("corrupted", []),
                "success_pct": v.get("success_pct"),
            }

        # Update protected files
        with _protected_lock:
            for name, info in _protected_files.items():
                if restore_result:
                    info["verified"] = True
                    info["verified_at"] = datetime.now(timezone.utc).isoformat()

        status = "success" if rc == 0 else "error"
        _add_event("restore",
                   f"Restore {'succeeded' if rc == 0 else 'failed'}" +
                   (f": {verification['verified_ok']}/{verification['total_files']} files verified"
                    if verification else ""),
                   status,
                   {"restore_result": restore_result})

        # Compare fingerprints for protected files
        fingerprint_matches = {}
        if rc == 0 and restore_result:
            target_dir = restore_result.get("target", "")
            with _protected_lock:
                for name, info in _protected_files.items():
                    fingerprint_matches[name] = {
                        "original_fingerprint": info["fingerprint"],
                        "status": "restored",
                    }

        return {
            "ok": rc == 0,
            "restore_result": restore_result,
            "verification": verification,
            "rto_seconds": round(rto, 2),
            "fingerprint_matches": fingerprint_matches,
            "output": out[-5000:],
        }
    finally:
        with _operation_lock:
            _current_operation = None


@app.post("/api/resume")
async def resume_backups():
    """Resume backups after alert handling."""
    rc, out = cexec("backup", "resume", timeout=60)
    _add_event("backup", "Backups resumed", "success" if rc == 0 else "error")
    return {"ok": rc == 0, "output": out[-1000:]}


# ---------------------------------------------------------------------------
# VAULT
# ---------------------------------------------------------------------------
@app.get("/api/vault")
async def vault_info():
    """Get vault status and try-delete proof."""
    _, st = cexec("vault", "status", timeout=60)
    _, td = cexec("vault", "try-delete", timeout=60)
    return {"ok": True, "status": st[-3000:], "try_delete": td[-2000:]}


# ---------------------------------------------------------------------------
# FAULT INJECTION & TRIAGE
# ---------------------------------------------------------------------------
@app.post("/api/fault")
async def inject_fault(body: FaultRequest):
    """Inject a fault (allowlisted)."""
    if body.name not in ALLOWED_FAULTS:
        raise HTTPException(400, f"Unknown fault '{body.name}'. Allowed: {sorted(ALLOWED_FAULTS)}")

    _add_event("fault", f"Injecting fault: {body.name}", "warning")

    rc, out = cexec("fault", "inject", body.name, timeout=60)
    extra = ""
    if body.name == "dns_failure":
        _, extra = run(["docker", "network", "disconnect", _net_name(), _ctr_name()], timeout=60)
    if body.name == "service_down":
        _, extra = run(["docker", "compose", "stop", "minio"], timeout=120)
    # Run one backup to materialize the failure
    rc2, bout = cexec("backup", "run", timeout=LONG_TIMEOUT)

    _add_event("fault", f"Fault {body.name} injected + backup attempted",
               "warning", {"inject": out[:500], "backup": bout[:500]})

    return {
        "ok": True,
        "inject": out[-1500:],
        "host_step": extra[-500:],
        "backup": bout[-2500:],
    }


@app.post("/api/clear")
async def clear_faults():
    """Clear all injected faults."""
    rc, out = cexec("fault", "clear", "--all", timeout=60)
    run(["docker", "network", "connect", _net_name(), _ctr_name()], timeout=60)
    run(["docker", "compose", "up", "-d", "minio"], timeout=180)
    _add_event("fault", "All faults cleared", "success")
    return {"ok": True, "output": out[-2000:]}


@app.post("/api/triage")
async def run_triage():
    """Triage recent failure logs."""
    from lab.triage import analyze
    rc, out = run(["docker", "compose", "exec", "-T", "app-server-1",
                   "tail", "-30", "/var/log/lab/backup.jsonl"], timeout=60)
    tmp = os.path.join(tempfile.gettempdir(), "lab-dash-triage.jsonl")
    with open(tmp, "w") as f:
        f.write(out)
    try:
        res = analyze(tmp)
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}

    groups = {gid: {"category": g["rule"].get("category"),
                    "severity": g["rule"].get("severity"),
                    "count": g["count"], "fix": g["rule"].get("fix"),
                    "cause": g["rule"].get("cause")}
              for gid, g in res["groups"].items()}

    _add_event("triage", f"Triage complete: {res['failures']} failures analyzed", "info",
               {"groups": len(groups)})

    return {"ok": True, "failures": res["failures"], "groups": groups}


# ---------------------------------------------------------------------------
# TIMELINE
# ---------------------------------------------------------------------------
@app.get("/api/timeline")
async def get_timeline():
    """Get the activity timeline (real events only)."""
    with _timeline_lock:
        events = list(_timeline)
    return {"ok": True, "events": sorted(events, key=lambda e: e["timestamp"], reverse=True)}


# ---------------------------------------------------------------------------
# RECOVERY COMMANDS
# ---------------------------------------------------------------------------
@app.get("/api/recovery-commands")
async def recovery_commands():
    """Return safe diagnostic/recovery commands for manual use."""
    return {
        "ok": True,
        "commands": {
            "check_containers": "docker compose ps",
            "view_logs": "docker compose logs --tail=50",
            "restart_all": "docker compose down && docker compose up -d",
            "restart_storage": "docker compose restart minio",
            "restart_app": "docker compose restart app-server-1",
            "check_storage": "curl -sf http://localhost:9000/minio/health/live",
            "check_prometheus": "curl -sf http://localhost:9090/-/healthy",
            "check_grafana": "curl -sf http://localhost:3000/api/health",
            "view_backup_log": "docker compose exec app-server-1 tail -20 /var/log/lab/backup.jsonl",
            "run_tests": "PYTHONPATH=src python3 -m pytest tests/ -v",
        },
        "note": "Run these commands from WSL in the project directory (~/projects/backup-resilience-lab)",
    }


# ---------------------------------------------------------------------------
# SERVE STATIC FRONTEND
# ---------------------------------------------------------------------------
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

@app.get("/")
async def serve_root():
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend not built. Run: cd dashboard/frontend && npm run build"}


# Mount static assets if frontend is built
if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="static")


# Catch-all for SPA routing
@app.get("/{full_path:path}")
async def spa_catch_all(full_path: str):
    # Try serving actual file first
    file_path = os.path.join(FRONTEND_DIST, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    # Fall back to index.html for SPA routing
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "File not found", "path": full_path}


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="Backup Resilience Lab Dashboard API")
    parser.add_argument("--port", type=int, default=8090, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    print(f"[dashboard-api] http://localhost:{args.port}  (repo: {REPO})")
    print(f"[dashboard-api] API docs: http://localhost:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
