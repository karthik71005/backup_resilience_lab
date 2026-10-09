"""Structured JSONL logging. One JSON object per line with ts, level, host, component, event, message."""
from __future__ import annotations
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

class JsonlLogger:
    def __init__(self, component: str, log_dir: str | Path | None = None, host: str | None = None):
        self.component = component
        self.host = host or os.environ.get("LAB_HOST") or socket.gethostname()
        ld = log_dir or os.environ.get("LAB_LOG_DIR", "/var/log/lab")
        self.log_dir = Path(ld)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / f"{component}.jsonl"

    def _write(self, level: str, event: str, message: str, **extra):
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "host": self.host,
            "component": self.component,
            "event": event,
            "message": message,
        }
        rec.update(extra)
        line = json.dumps(rec)
        with open(self.path, "a") as f:
            f.write(line + "\n")
        return rec

    def info(self, event: str, message: str, **kw):
        return self._write("INFO", event, message, **kw)

    def warning(self, event: str, message: str, **kw):
        return self._write("WARNING", event, message, **kw)

    def error(self, event: str, message: str, **kw):
        return self._write("ERROR", event, message, **kw)

def get_logger(component: str, log_dir=None, host=None) -> JsonlLogger:
    return JsonlLogger(component, log_dir=log_dir, host=host)
