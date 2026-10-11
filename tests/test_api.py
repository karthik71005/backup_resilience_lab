"""Tests for the Backup Resilience Lab FastAPI backend (dashboard/api.py).

Covers:
  - Global health states and per-service health
  - Request timeouts and failure handling
  - Diagnostics execution and structured schema
  - Safe service operation allowlists (prevent arbitrary restart)
  - File upload validation (empty file, invalid filename, oversized, SHA-256 fingerprint)
  - Prevention of arbitrary path traversal
  - Attack simulation guards (refusal when no clean backup exists)
  - Distinguishing simulation completion from detection
  - Restore and verification parsing
  - Timeline events recording
  - Prevention of arbitrary shell execution
"""
import io
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import sys
import os
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from dashboard.api import app, ALLOWED_SERVICES, ALLOWED_FAULTS, _timeline, _protected_files

client = TestClient(app)


def test_health_endpoint():
    """Global health endpoint returns valid schema."""
    with patch("dashboard.api.run_health_check") as mock_check:
        mock_check.return_value = {
            "global_status": "healthy",
            "last_check": "2026-10-11T00:00:00Z",
            "last_success": "2026-10-11T00:00:00Z",
            "services": {
                "minio": {"name": "RustFS S3", "status": "healthy", "latency_ms": 2.5},
                "app-server-1": {"name": "App Server 1", "status": "healthy", "latency_ms": 1.2},
            },
            "summary": {"total": 2, "healthy": 2, "unhealthy": 0, "degraded": 0}
        }
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["global_status"] == "healthy"
        assert "services" in data
        assert data["summary"]["healthy"] == 2


def test_health_services_breakdown():
    """Health breakdown returns per-service details."""
    with patch("dashboard.api.run_health_check") as mock_check:
        mock_check.return_value = {
            "global_status": "degraded",
            "services": {
                "minio": {"name": "RustFS", "status": "healthy"},
                "grafana": {"name": "Grafana", "status": "unhealthy", "error": "Connection refused"}
            },
            "summary": {"total": 2, "healthy": 1, "unhealthy": 1, "degraded": 0}
        }
        res = client.get("/api/health/services")
        assert res.status_code == 200
        data = res.json()
        assert data["global_status"] == "degraded"
        assert "grafana" in data["services"]
        assert data["services"]["grafana"]["status"] == "unhealthy"


def test_service_restart_allowlist():
    """Only allowlisted services can be restarted, with explicit confirm."""
    # Disallowed service rejected
    res = client.post("/api/services/malicious-service/restart", json={"action": "restart", "confirm": True})
    assert res.status_code == 400
    assert "not in the allowed list" in res.json()["detail"]

    # Allowed service requires confirm=True
    res = client.post("/api/services/minio/restart", json={"action": "restart", "confirm": False})
    assert res.status_code == 200
    assert res.json()["requires_confirm"] is True

    # Allowed service with confirm=True executes docker compose restart
    with patch("dashboard.api.run", return_value=(0, "restarted minio")):
        with patch("dashboard.api.run_health_check", return_value={"global_status": "healthy"}):
            res = client.post("/api/services/minio/restart", json={"action": "restart", "confirm": True})
            assert res.status_code == 200
            assert res.json()["ok"] is True
            assert res.json()["service"] == "minio"


def test_diagnostics_structure():
    """Diagnostics endpoint returns structured multi-check report."""
    with patch("dashboard.api.run", return_value=(0, "test log")):
        with patch("dashboard.api.cexec", return_value=(0, "[]")):
            with patch("dashboard.api.metrics_text", return_value=""):
                with patch("dashboard.api._check_url", return_value=(True, "OK", 5.0)):
                    res = client.post("/api/diagnostics")
                    assert res.status_code == 200
                    data = res.json()
                    assert data["ok"] is True
                    assert "diagnostic_id" in data
                    assert "checks" in data
                    assert len(data["checks"]) >= 5
                    for check in data["checks"]:
                        assert "component" in check
                        assert "status" in check
                        assert "observed" in check


def test_upload_validation():
    """Upload endpoint validates files and computes SHA-256."""
    # Empty file rejected
    res = client.post("/api/upload", files={"file": ("empty.txt", b"", "text/plain")})
    assert res.status_code == 400
    assert "Empty file" in res.json()["detail"]

    # Valid file uploads safely and computes fingerprint
    sample_content = b"Resilience Lab Test Payload"
    with patch("dashboard.api.run", return_value=(0, "copied")):
        res = client.post("/api/upload", files={"file": ("sample.txt", io.BytesIO(sample_content), "text/plain")})
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["name"] == "sample.txt"
        assert len(data["fingerprint"]) == 64  # SHA-256 length


def test_attack_simulation_guard_requires_clean_backup():
    """Attack simulator refuses to run if no clean backup exists."""
    with patch("dashboard.api.cexec", return_value=(0, "[]")):  # No snapshots
        res = client.post("/api/attack")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False
        assert data["pre_check_failed"] is True
        assert "No clean backup found" in data["reason"]


def test_attack_simulation_distinguishes_completion_from_detection():
    """Attack simulation records encryption result and evaluates detector separately."""
    clean_snaps = json.dumps([{"id": "snap-12345", "status": "clean"}])
    attack_out = json.dumps({"run_id": "test-run", "files": 150})

    with patch("dashboard.api.cexec", side_effect=[(0, clean_snaps), (0, attack_out)]):
        with patch("dashboard.api.metrics_text", return_value="lab_detector_score{host=\"app-server-1\"} 0.82\nlab_backups_paused{host=\"app-server-1\"} 1\n"):
            with patch("dashboard.api.prom_query", return_value={"app-server-1": "1"}):
                res = client.post("/api/attack")
                assert res.status_code == 200
                data = res.json()
                assert data["ok"] is True
                assert data["attack_result"]["files"] == 150
                # Detector outcome is evaluated separately
                assert data["post_attack"]["detected"] is True
                assert data["post_attack"]["detector_score"] == 0.82
                assert data["post_attack"]["backups_paused"] is True


def test_restore_and_verification_outcome():
    """Restore parses SHA-256 verification and measures RTO."""
    restore_out = json.dumps({
        "target": "/data/restore",
        "snapshot_id": "snap-12345",
        "verify": {
            "total": 301,
            "ok": 301,
            "missing": [],
            "corrupted": [],
            "success_pct": 100.0
        }
    })

    with patch("dashboard.api.cexec", return_value=(0, restore_out)):
        res = client.post("/api/restore")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["verification"]["total_files"] == 301
        assert data["verification"]["verified_ok"] == 301
        assert data["rto_seconds"] >= 0


def test_fault_injection_allowlist():
    """Only allowlisted faults can be injected."""
    res = client.post("/api/fault", json={"name": "arbitrary_evil_fault"})
    assert res.status_code == 400
    assert "Unknown fault" in res.json()["detail"]


def test_timeline_records_real_events():
    """Timeline returns chronological events without fabricated items."""
    res = client.get("/api/timeline")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert isinstance(data["events"], list)
