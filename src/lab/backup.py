"""Backup runner: restic backup /data + manifest upload + SQLite record."""
from __future__ import annotations
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .logging_setup import get_logger
from .manifest import build_manifest
from . import state as st

def _env(cfg, extra: dict | None = None) -> dict:
    e = os.environ.copy()
    e.setdefault("RESTIC_REPOSITORY", f"s3:{cfg.s3_endpoint}/{cfg.primary_bucket}/{cfg.host}")
    # restic S3 vars
    if "AWS_ACCESS_KEY_ID" not in e and "MINIO_ROOT_USER" in e:
        e["AWS_ACCESS_KEY_ID"] = e["MINIO_ROOT_USER"]
    if "AWS_SECRET_ACCESS_KEY" not in e and "MINIO_ROOT_PASSWORD" in e:
        e["AWS_SECRET_ACCESS_KEY"] = e["MINIO_ROOT_PASSWORD"]
    if extra:
        e.update(extra)
    return e

def _upload_manifest_s3(cfg, manifest: dict, snapshot_id: str):
    """Upload manifest JSON to primary bucket via boto3."""
    import boto3
    s3 = boto3.client("s3", endpoint_url=cfg.s3_endpoint,
                      aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("MINIO_ROOT_USER", "minioadmin"),
                      aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123"))
    key = f"{cfg.manifest_prefix}/{cfg.host}/{snapshot_id}.json"
    s3.put_object(Bucket=cfg.primary_bucket, Key=key, Body=json.dumps(manifest).encode())
    return key

def run_backup(cfg=None, log_dir=None, data_dir=None) -> dict:
    cfg = cfg or load_config()
    log = get_logger("backup", log_dir=log_dir or cfg.log_dir, host=cfg.host)
    t0 = time.time()
    # paused?
    if st.is_paused(cfg.state_db):
        log.info("backup_skipped", "Backups paused, skipping run")
        return {"skipped": True}
    # anomaly deferral (Oct 2026): do not snapshot -- or relearn baselines --
    # while the detector score is elevated; a mid-attack backup would record
    # dirty data as clean and poison entropy baselines, suppressing detection.
    try:
        defer_at = float(getattr(cfg, "anomaly_defer_score", 0.3))
        cur_score = float(st.get_flag(cfg.state_db, "detector_score", "0") or 0)
    except Exception:
        defer_at, cur_score = 0.3, 0.0
    if cur_score >= defer_at:
        log.warning("backup_deferred", f"detector score {cur_score:.2f} >= {defer_at}, deferring backup",
                    score=cur_score)
        return {"skipped": True, "deferred": True, "score": cur_score}
    ddir = data_dir or cfg.data_dir
    # 1. manifest
    manifest = build_manifest(ddir)
    # 2. restic backup
    env = _env(cfg)
    # ensure repo init (idempotent)
    subprocess.run(["restic", "init"], env=env, capture_output=True)
    cmd = ["restic", "backup", ddir, "--tag", "lab", "--json"]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    dur = time.time() - t0
    if proc.returncode != 0:
        log.error("backup_failed", f"restic backup failed after {dur:.1f}s",
                  exit_code=proc.returncode, raw=(proc.stderr or "")[-4000:], duration_s=round(dur, 2))
        try:
            cur = int(st.get_flag(cfg.state_db, "backup_failures", "0") or 0)
            st.set_flag(cfg.state_db, "backup_failures", str(cur + 1))
        except Exception:
            pass
        try:
            from .exporter import inc_backup_failure
            inc_backup_failure("unknown")
        except Exception:
            pass
        return {"ok": False, "exit_code": proc.returncode, "stderr": proc.stderr}
    # parse snapshot id from last JSON line with snapshot_id
    snap_id = None
    for line in proc.stdout.strip().splitlines()[::-1]:
        try:
            obj = json.loads(line)
            if "snapshot_id" in obj:
                snap_id = obj["snapshot_id"]
                break
        except Exception:
            continue
    if not snap_id:
        snap_id = f"manual-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    taken_at = datetime.now(timezone.utc).isoformat()
    # 3. upload manifest
    try:
        _upload_manifest_s3(cfg, manifest, snap_id)
    except Exception as e:
        log.warning("manifest_upload_failed", f"manifest upload failed: {e}", raw=str(e)[:2000])
    # 4. sqlite
    st.insert_snapshot(cfg.state_db, snap_id, cfg.host, taken_at, "clean", manifest["count"], manifest["bytes"])
    # 5. update baselines only after clean backup
    from .features import file_entropy
    root = Path(ddir)
    seen = set()
    for ent in manifest["files"]:
        if ent.get("sha256"):
            seen.add(ent["path"])
            try:
                e = file_entropy(root / ent["path"])
                st.upsert_baseline(cfg.state_db, ent["path"], e)
            except Exception:
                pass
    # prune baselines for files that no longer exist (bounded table, no stale paths).
    # Guard: never prune on an empty manifest (could be a fault, not deletions).
    try:
        if seen:
            c = st.connect(cfg.state_db)
            c.execute(f"DELETE FROM baselines WHERE path NOT IN ({','.join('?' * len(seen))})", tuple(seen))
            c.commit(); c.close()
    except Exception:
        pass
    log.info("backup_ok", f"snapshot {snap_id[:8]} files={manifest['count']} bytes={manifest['bytes']}",
             snapshot_id=snap_id, files=manifest["count"], bytes=manifest["bytes"], duration_s=round(dur, 2))
    try:
        st.set_flag(cfg.state_db, "last_success_ts", str(time.time()))
        st.set_flag(cfg.state_db, "last_duration", str(round(dur, 2)))
    except Exception:
        pass
    try:
        from .exporter import set_last_success, observe_backup_duration
        set_last_success(time.time())
        observe_backup_duration(dur)
    except Exception:
        pass
    # periodic check
    n = len(st.list_snapshots(cfg.state_db, cfg.host))
    if n % cfg.backup_check_every_n == 0:
        chk = subprocess.run(["restic", "check"], env=env, capture_output=True, text=True)
        log.info("repo_check", f"restic check rc={chk.returncode}", exit_code=chk.returncode, raw=(chk.stderr or "")[-2000:])
    return {"ok": True, "snapshot_id": snap_id, "files": manifest["count"], "bytes": manifest["bytes"], "duration_s": dur}

def loop(cfg=None):
    cfg = cfg or load_config()
    log = get_logger("backup", log_dir=cfg.log_dir, host=cfg.host)
    log.info("scheduler_start", f"backup every {cfg.backup_interval_seconds}s")
    while True:
        try:
            run_backup(cfg)
        except Exception as e:
            log.error("backup_exception", str(e), raw=str(e)[:2000])
        time.sleep(cfg.backup_interval_seconds)
