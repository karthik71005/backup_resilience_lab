"""Restore from newest clean snapshot + verify + RTO/RPO."""
from __future__ import annotations
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3

from .config import load_config
from .logging_setup import get_logger
from . import state as st
from .verify import verify_restore

def _env(cfg) -> dict:
    e = os.environ.copy()
    e.setdefault("RESTIC_REPOSITORY", f"s3:{cfg.s3_endpoint}/{cfg.primary_bucket}/{cfg.host}")
    if "AWS_ACCESS_KEY_ID" not in e and "MINIO_ROOT_USER" in e:
        e["AWS_ACCESS_KEY_ID"] = e["MINIO_ROOT_USER"]
    if "AWS_SECRET_ACCESS_KEY" not in e and "MINIO_ROOT_PASSWORD" in e:
        e["AWS_SECRET_ACCESS_KEY"] = e["MINIO_ROOT_PASSWORD"]
    return e

def _download_manifest(cfg, snap_id: str, host: str) -> dict:
    s3 = boto3.client("s3", endpoint_url=cfg.s3_endpoint,
                      aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("MINIO_ROOT_USER", "minioadmin"),
                      aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123"))
    key = f"{cfg.manifest_prefix}/{host}/{snap_id}.json"
    obj = s3.get_object(Bucket=cfg.primary_bucket, Key=key)
    return json.loads(obj["Body"].read())

def _attack_start_from_logs(log_dir: str | Path) -> str | None:
    lp = Path(log_dir)
    last = None
    for f in sorted(lp.glob("*.jsonl")):
        try:
            for line in open(f):
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("event") in ("attack_start",) and rec.get("attack_start"):
                    last = rec["attack_start"]
        except FileNotFoundError:
            continue
    return last

def _detected_at_from_logs(log_dir) -> str | None:
    lp = Path(log_dir)
    last = None
    for f in sorted(lp.glob("*.jsonl")):
        try:
            for line in open(f):
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("event") == "alert_raised" and rec.get("detected_at"):
                    last = rec["detected_at"]
        except FileNotFoundError:
            continue
    return last

def run_restore(cfg=None, host: str | None = None, latest_clean: bool = True, snapshot_id: str | None = None) -> dict:
    cfg = cfg or load_config()
    host = host or cfg.host
    log = get_logger("restore", log_dir=cfg.log_dir, host=cfg.host)
    t_start = time.time()
    restore_started_at = datetime.now(timezone.utc).isoformat()
    if latest_clean:
        snap = st.get_latest_clean(cfg.state_db, host)
        if not snap:
            raise SystemExit(f"No clean snapshot for host {host}")
        snapshot_id = snap["id"]
        snap_taken = snap["taken_at"]
    else:
        snap_taken = restore_started_at
    run_id = uuid.uuid4().hex[:8]
    target = Path(cfg.restore_base) / run_id
    target.mkdir(parents=True, exist_ok=True)
    env = _env(cfg)
    # restic restore: repo path includes host prefix; snapshot id within that repo
    # Our backup used RESTIC_REPOSITORY with host suffix, so restore same.
    env_host = os.environ.copy()
    env_host.update(env)
    # If host differs from cfg.host, adjust repo URL
    repo = f"s3:{cfg.s3_endpoint}/{cfg.primary_bucket}/{host}"
    env_host["RESTIC_REPOSITORY"] = repo
    proc = subprocess.run(["restic", "restore", snapshot_id, "--target", str(target)], env=env_host, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("restore_failed", f"restic restore {snapshot_id[:8]} failed", exit_code=proc.returncode, raw=(proc.stderr or "")[-4000:])
        raise SystemExit(f"restore failed: {proc.stderr[-1000:]}")
    manifest = _download_manifest(cfg, snapshot_id, host)
    result = verify_restore(target, manifest)
    verified_at = datetime.now(timezone.utc).isoformat()
    rto = time.time() - t_start
    # RPO + detection latency from logs
    attack_start = _attack_start_from_logs(cfg.log_dir)
    detected_at = _detected_at_from_logs(cfg.log_dir)
    def _dt(s):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    rpo = ((_dt(attack_start) - _dt(snap_taken)).total_seconds()) if (attack_start and snap_taken and _dt(attack_start) and _dt(snap_taken)) else None
    det_lat = ((_dt(detected_at) - _dt(attack_start)).total_seconds()) if (attack_start and detected_at and _dt(attack_start) and _dt(detected_at)) else None
    log.info("restore_ok", f"restored {snapshot_id[:8]} ok={result['ok']}/{result['total']} rto={rto:.1f}s",
             snapshot_id=snapshot_id, target=str(target), rto_s=round(rto, 2), rpo_s=rpo,
             detection_latency_s=det_lat, success_pct=result["success_pct"])
    try:
        from .exporter import set_rto
        set_rto(rto)
        st.set_flag(cfg.state_db, "last_rto", str(round(rto, 2)))
    except Exception:
        pass
    out = {"snapshot_id": snapshot_id, "target": str(target), "verify": result,
           "rto_s": round(rto, 2), "rpo_s": rpo, "detection_latency_s": det_lat,
           "restore_started_at": restore_started_at, "verified_at": verified_at,
           "attack_start": attack_start, "detected_at": detected_at}
    print(json.dumps(out, indent=2))
    return out
