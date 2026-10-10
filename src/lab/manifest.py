"""Manifest: walk /data, SHA-256 each file."""
from __future__ import annotations
import hashlib
from pathlib import Path

def sha256_file(p: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def build_manifest(data_dir: str | Path):
    import os
    root = Path(data_dir)
    entries = []
    total_bytes = 0
    for p in sorted(root.rglob("*")):
        # rglob silently skips unreadable directories, so probe every dir
        # explicitly (chmod 000 on a dir hides its whole subtree).
        if p.is_dir() and not p.is_symlink():
            try:
                with os.scandir(p):
                    pass
            except (PermissionError, FileNotFoundError):
                rel = str(p.relative_to(root))
                entries.append({"path": rel, "size": 0, "sha256": "", "mtime": 0, "error": "permission_denied"})
            continue
        if p.is_file() and not p.is_symlink():
            try:
                st = p.stat()
                digest = sha256_file(p)
                rel = str(p.relative_to(root))
                entries.append({"path": rel, "size": st.st_size, "sha256": digest, "mtime": st.st_mtime})
                total_bytes += st.st_size
            except (PermissionError, FileNotFoundError):
                entries.append({"path": str(p.relative_to(root)), "size": 0, "sha256": "", "mtime": 0, "error": "permission_denied"})
    return {"files": entries, "count": len(entries), "bytes": total_bytes}
