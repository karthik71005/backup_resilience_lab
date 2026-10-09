"""Verify: compare restored tree against manifest by SHA-256."""
from __future__ import annotations
from pathlib import Path
from .manifest import sha256_file

def verify_restore(restored_root: str | Path, manifest: dict) -> dict:
    root = Path(restored_root)
    # manifest paths are relative to /data; restic restore reproduces full path? handle both
    expected = {e["path"]: e for e in manifest.get("files", [])}
    missing, corrupted, ok = [], [], []
    for rel, ent in expected.items():
        cands = [root / rel, root / "data" / rel]
        found = next((c for c in cands if c.is_file()), None)
        if not found:
            # search by name fallback
            matches = list(root.rglob(Path(rel).name))
            found = matches[0] if matches else None
        if not found or not found.is_file():
            missing.append(rel)
            continue
        try:
            digest = sha256_file(found)
        except Exception:
            corrupted.append(rel)
            continue
        if digest == ent.get("sha256"):
            ok.append(rel)
        else:
            corrupted.append(rel)
    total = len(expected)
    pct = (len(ok) / total * 100) if total else 100.0
    return {"total": total, "ok": len(ok), "missing": missing, "corrupted": corrupted, "success_pct": pct}
