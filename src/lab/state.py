"""SQLite state: snapshots, baselines, kv flags, cases index."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots(
  id TEXT PRIMARY KEY,
  host TEXT NOT NULL,
  taken_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'clean',
  files INTEGER DEFAULT 0,
  bytes INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS baselines(
  path TEXT PRIMARY KEY,
  entropy REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases(
  id TEXT PRIMARY KEY,
  title TEXT,
  severity TEXT,
  category TEXT,
  host TEXT,
  created_at TEXT,
  path TEXT
);
"""

def connect(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def insert_snapshot(db_path, snap_id: str, host: str, taken_at: str, status: str = "clean", files: int = 0, nbytes: int = 0):
    c = connect(db_path)
    c.execute("INSERT OR REPLACE INTO snapshots(id,host,taken_at,status,files,bytes) VALUES(?,?,?,?,?,?)",
              (snap_id, host, taken_at, status, files, nbytes))
    c.commit(); c.close()

def list_snapshots(db_path, host: str | None = None):
    c = connect(db_path)
    if host:
        rows = c.execute("SELECT * FROM snapshots WHERE host=? ORDER BY taken_at", (host,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM snapshots ORDER BY taken_at").fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_latest_clean(db_path, host: str):
    c = connect(db_path)
    row = c.execute("SELECT * FROM snapshots WHERE host=? AND status='clean' ORDER BY taken_at DESC LIMIT 1", (host,)).fetchone()
    c.close()
    return dict(row) if row else None

def mark_suspect_since(db_path, attack_start_iso: str, safety_margin_seconds: int = 5):
    """Mark snapshots with taken_at >= attack_start - margin as suspect. Returns count."""
    from datetime import timedelta
    c = connect(db_path)
    # parse attack_start
    try:
        atk = datetime.fromisoformat(attack_start_iso.replace("Z", "+00:00"))
    except Exception:
        atk = datetime.now(timezone.utc)
    cutoff = (atk - timedelta(seconds=safety_margin_seconds)).isoformat()
    cur = c.execute("UPDATE snapshots SET status='suspect' WHERE taken_at >= ? AND status='clean'", (cutoff,))
    n = cur.rowcount
    c.commit(); c.close()
    return n

def set_flag(db_path, key: str, value: str):
    c = connect(db_path)
    c.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (key, value))
    c.commit(); c.close()

def get_flag(db_path, key: str, default: str | None = None):
    c = connect(db_path)
    row = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    c.close()
    return row["value"] if row else default

def is_paused(db_path) -> bool:
    return get_flag(db_path, "backups_paused", "false") == "true"

def set_paused(db_path, paused: bool):
    set_flag(db_path, "backups_paused", "true" if paused else "false")

def upsert_baseline(db_path, path: str, entropy: float):
    c = connect(db_path)
    c.execute("INSERT OR REPLACE INTO baselines(path,entropy) VALUES(?,?)", (path, entropy))
    c.commit(); c.close()

def get_baseline(db_path, path: str):
    c = connect(db_path)
    row = c.execute("SELECT entropy FROM baselines WHERE path=?", (path,)).fetchone()
    c.close()
    return row["entropy"] if row else None

def get_all_baselines(db_path) -> dict:
    c = connect(db_path)
    rows = c.execute("SELECT path,entropy FROM baselines").fetchall()
    c.close()
    return {r["path"]: r["entropy"] for r in rows}

def index_case(db_path, case_id, title, severity, category, host, path):
    c = connect(db_path)
    c.execute("INSERT OR REPLACE INTO cases(id,title,severity,category,host,created_at,path) VALUES(?,?,?,?,?,?,?)",
              (case_id, title, severity, category, host, now_iso(), path))
    c.commit(); c.close()
