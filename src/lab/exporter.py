"""Prometheus exporter (spec Section 10).

Design note (Oct 2026): exporter, detector and backup loop are separate
processes, so in-memory prometheus_client values set in one process are
invisible to the scrape endpoint. The exporter therefore acts as a pull
adapter: gauges/counters are rebuilt on every /metrics scrape from the
SQLite state DB (snapshots, kv flags) and by tailing the shared JSONL logs
(filtered by host). Metric names/types match the spec exactly.
"""
from __future__ import annotations
import json
import os
import threading
from pathlib import Path
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

LAB_BACKUP_LAST_SUCCESS = Gauge("lab_backup_last_success_timestamp", "Unix time of last good backup", ["host"])
LAB_BACKUP_DURATION = Histogram("lab_backup_duration_seconds", "Backup runtime", ["host"])
LAB_BACKUP_FAILURES = Counter("lab_backup_failures_total", "Failures by category", ["category", "host"])
LAB_SNAPSHOTS = Gauge("lab_snapshots_total", "Snapshots by status", ["status", "host"])
LAB_REPO_SIZE = Gauge("lab_repo_size_bytes", "Repository size", ["host"])
LAB_DETECTOR_SCORE = Gauge("lab_detector_score", "Current score", ["host"])
LAB_ALERTS = Counter("lab_alerts_total", "Ransomware alerts", ["host"])
LAB_PAUSED = Gauge("lab_backups_paused", "0 or 1", ["host"])
LAB_RTO = Gauge("lab_last_restore_rto_seconds", "Last RTO", ["host"])

import os as _os
_HOST = _os.environ.get("LAB_HOST", "app-server-1")

_lock = threading.Lock()
_tail_offsets: dict[str, int] = {}
_last_alerts: dict[str, int] = {}
_last_failures: dict[str, int] = {}

def _h(host=None):
    return host or _HOST

def set_last_success(ts: float, host=None):
    try:
        LAB_BACKUP_LAST_SUCCESS.labels(host=_h(host)).set(ts)
    except Exception:
        pass

def observe_backup_duration(d: float, host=None):
    try:
        LAB_BACKUP_DURATION.labels(host=_h(host)).observe(d)
    except Exception:
        pass

def inc_backup_failure(category: str, host=None):
    try:
        LAB_BACKUP_FAILURES.labels(category=category, host=_h(host)).inc()
    except Exception:
        pass

def set_snapshots(clean: int, suspect: int, host=None):
    try:
        LAB_SNAPSHOTS.labels(status="clean", host=_h(host)).set(clean)
        LAB_SNAPSHOTS.labels(status="suspect", host=_h(host)).set(suspect)
    except Exception:
        pass

def set_repo_size(n: float, host=None):
    try:
        LAB_REPO_SIZE.labels(host=_h(host)).set(n)
    except Exception:
        pass

def set_detector_score(s: float, host=None):
    try:
        LAB_DETECTOR_SCORE.labels(host=_h(host)).set(s)
    except Exception:
        pass

def inc_alert(host=None):
    try:
        LAB_ALERTS.labels(host=_h(host)).inc()
    except Exception:
        pass

def set_paused(p: bool, host=None):
    try:
        LAB_PAUSED.labels(host=_h(host)).set(1 if p else 0)
    except Exception:
        pass

def set_rto(s: float, host=None):
    try:
        LAB_RTO.labels(host=_h(host)).set(s)
    except Exception:
        pass

def _parse_ts(s: str) -> float | None:
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

def refresh_from_state(cfg, rules=None) -> None:
    """Rebuild exported values from SQLite + logs. Called on every scrape."""
    from . import state as st
    host = cfg.host
    with _lock:
        try:
            rows = st.list_snapshots(cfg.state_db, host)
        except Exception:
            rows = []
        clean = [r for r in rows if r["status"] == "clean"]
        susp = [r for r in rows if r["status"] == "suspect"]
        set_snapshots(len(clean), len(susp), host)
        if clean:
            ts = max((_parse_ts(r["taken_at"]) or 0) for r in clean)
            if ts:
                set_last_success(ts, host)
        set_repo_size(sum(r.get("bytes", 0) or 0 for r in rows), host)
        try:
            paused = st.is_paused(cfg.state_db)
        except Exception:
            paused = False
        set_paused(paused, host)
        try:
            score = float(st.get_flag(cfg.state_db, "detector_score", "0") or 0)
        except Exception:
            score = 0.0
        set_detector_score(score, host)
        try:
            rto = float(st.get_flag(cfg.state_db, "last_rto", "0") or 0)
        except Exception:
            rto = 0.0
        if rto:
            set_rto(rto, host)
        # alerts counter follows kv (inc by delta so Counter stays monotonic)
        try:
            want = int(st.get_flag(cfg.state_db, "alerts_total", "0") or 0)
        except Exception:
            want = 0
        got = _last_alerts.get(host, 0)
        if want > got:
            for _ in range(want - got):
                inc_alert(host)
            _last_alerts[host] = want
        # tail backup.jsonl for new durations + failures (host-filtered)
        logf = str(Path(cfg.log_dir) / "backup.jsonl")
        try:
            off = _tail_offsets.get(logf, 0)
            with open(logf) as f:
                f.seek(off)
                new_lines = f.readlines()
                _tail_offsets[logf] = f.tell()
        except FileNotFoundError:
            new_lines = []
        for line in new_lines:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("host") != host:
                continue
            if rec.get("event") == "backup_ok" and rec.get("duration_s") is not None:
                try:
                    observe_backup_duration(float(rec["duration_s"]), host)
                except Exception:
                    pass
            if rec.get("event") in ("backup_failed", "backup_exception") or rec.get("level") == "ERROR":
                cat = "unknown"
                try:
                    if rules is None:
                        from .triage import load_rules, classify_record
                        rules = load_rules()
                    rule = classify_record(rec, rules)
                    cat = (rule or {}).get("category", "unknown")
                except Exception:
                    pass
                inc_backup_failure(cat, host)

def serve(port: int = 8000, cfg=None):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from .config import load_config
    cfg = cfg or load_config()
    rules = None
    try:
        from .triage import load_rules
        rules = load_rules()
    except Exception:
        pass

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/metrics":
                self.send_response(404); self.end_headers(); return
            try:
                refresh_from_state(cfg, rules)
            except Exception:
                pass
            body = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass
    print(f"[exporter] :{port} host={cfg.host}")
    HTTPServer(("0.0.0.0", port), H).serve_forever()
