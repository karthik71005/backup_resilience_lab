"""Vault helpers: status + try-delete (must be refused under GOVERNANCE retention)."""
from __future__ import annotations
import os
import botocore.exceptions
import boto3
from .config import load_config

def _client(cfg):
    return boto3.client("s3", endpoint_url=cfg.s3_endpoint,
                        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("MINIO_ROOT_USER", "minioadmin"),
                        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123"))

def vault_status(cfg=None) -> dict:
    cfg = cfg or load_config()
    s3 = _client(cfg)
    objs = s3.list_objects_v2(Bucket=cfg.vault_bucket).get("Contents", [])
    try:
        lock = s3.get_object_lock_configuration(Bucket=cfg.vault_bucket)
    except Exception as e:
        lock = {"error": str(e)[:500]}
    try:
        ver = s3.get_bucket_versioning(Bucket=cfg.vault_bucket)
    except Exception as e:
        ver = {"error": str(e)[:500]}
    return {"bucket": cfg.vault_bucket, "objects": len(objs), "lock": lock, "versioning": ver}

def _retention_of(s3, bucket: str, key: str):
    try:
        r = s3.get_object_retention(Bucket=bucket, Key=key)
        return r.get("Retention")
    except Exception:
        return None

def vault_try_delete(cfg=None, key: str | None = None) -> dict:
    """Attempt to destroy a versioned vault object. Under GOVERNANCE retention
    the version-specific delete must be refused (AccessDenied). Note: a plain
    delete without VersionId only hides the key behind a delete marker on
    versioned buckets, so we target the live VersionId directly — that is the
    real WORM guarantee (spec Section 6, rule 8 verified against RustFS)."""
    cfg = cfg or load_config()
    s3 = _client(cfg)
    if key is None:
        objs = s3.list_objects_v2(Bucket=cfg.vault_bucket, MaxKeys=20).get("Contents", [])
        if not objs:
            return {"ok": False, "refused": False, "message": "vault empty - nothing to delete (run a backup + vault-sync first)"}
        key = objs[0]["Key"]
        for o in objs:
            if o["Key"].startswith(cfg.manifest_prefix + "/") and _retention_of(s3, cfg.vault_bucket, o["Key"]):
                key = o["Key"]
                break
    retention = _retention_of(s3, cfg.vault_bucket, key)
    # resolve live version id
    version_id = None
    try:
        vers = s3.list_object_versions(Bucket=cfg.vault_bucket, Prefix=key).get("Versions", [])
        for v in vers:
            if v["Key"] == key and v.get("IsLatest"):
                version_id = v["VersionId"]
                break
        if version_id is None and vers:
            version_id = vers[0]["VersionId"]
    except Exception as e:
        return {"ok": False, "refused": False, "key": key, "message": f"cannot list versions: {e}"[:500]}
    try:
        if version_id:
            s3.delete_object(Bucket=cfg.vault_bucket, Key=key, VersionId=version_id)
        else:
            s3.delete_object(Bucket=cfg.vault_bucket, Key=key)
        return {"ok": True, "refused": False, "key": key, "version_id": version_id,
                "retention": retention,
                "message": "deleted (no retention on this version or retention expired)"}
    except botocore.exceptions.ClientError as e:
        return {"ok": False, "refused": True, "key": key, "version_id": version_id,
                "retention": retention, "message": str(e)[:1000]}
