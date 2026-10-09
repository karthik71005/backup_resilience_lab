"""Central config loader: config/lab.yaml + env overrides."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
import yaml

DEFAULT_CONFIG_PATHS = [
    Path("config/lab.yaml"),
    Path(__file__).resolve().parents[2] / "config" / "lab.yaml",
    Path.home() / "projects" / "backup-resilience-lab" / "config" / "lab.yaml",
]

@dataclass
class LabConfig:
    host: str = "app-server-1"
    data_dir: str = "/data"
    victim_dir: str = "/data/victim"
    log_dir: str = "/var/log/lab"
    state_db: str = "/var/lib/lab/state.db"
    restore_base: str = "/restore"
    s3_endpoint: str = "http://minio:9000"
    primary_bucket: str = "backup-primary"
    vault_bucket: str = "backup-vault"
    manifest_prefix: str = "manifests"
    backup_interval_seconds: int = 120
    backup_check_every_n: int = 5
    vault_sync_seconds: int = 60
    window_seconds: int = 10
    score_threshold: float = 0.6
    consecutive_windows: int = 2
    safety_margin_seconds: int = 5
    weights: dict = field(default_factory=lambda: {"mod_rate": 0.35, "high_entropy_ratio": 0.35, "ext_change": 0.20, "note_files": 0.10})
    mod_rate_norm: float = 50.0
    ext_change_norm: float = 10.0
    entropy_high: float = 7.5
    entropy_baseline_low: float = 7.0
    entropy_jump_min: float = 1.5
    anomaly_defer_score: float = 0.3
    sim_rate_files_per_sec: float = 15.0
    sim_delay_seconds: float = 2.0
    p1_no_backup_intervals: int = 3

def _find_config(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    env = os.environ.get("LAB_CONFIG")
    if env and Path(env).exists():
        return Path(env)
    for p in DEFAULT_CONFIG_PATHS:
        if p.exists():
            return p
    # fallback: relative to cwd
    c = Path("config/lab.yaml")
    return c if c.exists() else None

def load_config(path: str | None = None) -> LabConfig:
    cfg = LabConfig()
    found = _find_config(path)
    data: dict = {}
    if found:
        data = yaml.safe_load(found.read_text()) or {}
    else:
        data = {}
    for k, v in data.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    # env overrides
    cfg.host = os.environ.get("LAB_HOST", cfg.host)
    cfg.data_dir = os.environ.get("LAB_DATA_DIR", cfg.data_dir)
    cfg.victim_dir = os.environ.get("LAB_VICTIM_DIR", cfg.victim_dir)
    cfg.log_dir = os.environ.get("LAB_LOG_DIR", cfg.log_dir)
    cfg.state_db = os.environ.get("LAB_STATE_DB", cfg.state_db)
    cfg.s3_endpoint = os.environ.get("S3_ENDPOINT", cfg.s3_endpoint)
    return cfg
