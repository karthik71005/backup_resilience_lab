"""Shannon entropy + sliding-window features (spec Section 8)."""
from __future__ import annotations
import math
from collections import Counter
from pathlib import Path

def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    ent = 0.0
    for c in counts.values():
        p = c / n
        ent -= p * math.log2(p)
    return ent

def file_entropy(path: str | Path, first_kb: int = 64) -> float:
    p = Path(path)
    try:
        with open(p, "rb") as f:
            data = f.read(first_kb * 1024)
        return shannon_entropy(data)
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        return 0.0

def compute_window_features(events: list[dict], baselines: dict, cfg) -> dict:
    """events: [{path, kind, entropy_now, ts}]. Returns mod_rate, entropy_jump, high_entropy_ratio, ext_change, note_files + score."""
    mod_files = {e.get("path") for e in events if e.get("kind") in ("modified", "created", "moved")}
    mod_rate = len(mod_files)
    # Group by file identity (moved events link back to their source path so
    # the baseline follows the rename; Oct 2026 race fix: the handler reads
    # modified files after ransomware has renamed them, so per-event entropy
    # for modifies is stale 0.0 while the move carries the real entropy).
    by_ident: dict[str, list] = {}
    for e in events:
        if e.get("kind") not in ("modified", "created", "moved"):
            continue
        ident = e.get("src") or e.get("path")
        by_ident.setdefault(ident, []).append(e)
    jumps = []
    high = 0
    with_base = 0
    jump_min = float(getattr(cfg, "entropy_jump_min", 1.5))
    for ident, evs in by_ident.items():
        base = baselines.get(ident)
        if base is None:
            # No baseline (new file or rename from unknown source):
            # still counts toward mod_rate burst signal, but cannot inform the
            # jump ratio.
            continue
        with_base += 1
        now = max((e.get("entropy_now") or 0.0) for e in evs)
        jump = now - base
        jumps.append(jump)
        # High-entropy signal (Oct 2026: baseline-relative OR absolute).
        # Absolute 7.5 alone misses small files: measured AES-CTR ciphertext
        # entropy is only ~7.4-7.7 for sub-KB files (short-sample estimate),
        # while their jump over a text baseline is +2.5..3.5 bits. Requiring
        # base < baseline_low keeps already-compressed files (zip/jpg)
        # excluded in both branches.
        if base < cfg.entropy_baseline_low and (
            now >= cfg.entropy_high or jump >= jump_min
        ):
            high += 1
    entropy_jump = sum(jumps) / len(jumps) if jumps else 0.0
    high_entropy_ratio = (high / with_base) if with_base else 0.0
    # ext_change: renames to previously unseen extension
    ext_change = sum(1 for e in events if e.get("kind") == "moved" and e.get("new_ext_unseen"))
    # note_files: new files with identical content (ransom note pattern)
    contents: dict = {}
    for e in events:
        if e.get("kind") == "created" and e.get("content_hash"):
            contents.setdefault(e["content_hash"], 0)
            contents[e["content_hash"]] += 1
    note_files = sum(1 for v in contents.values() if v >= 2)
    # score
    w = cfg.weights
    score = (w.get("mod_rate", 0.35) * min(mod_rate / cfg.mod_rate_norm, 1.0)
             + w.get("high_entropy_ratio", 0.35) * high_entropy_ratio
             + w.get("ext_change", 0.20) * min(ext_change / cfg.ext_change_norm, 1.0)
             + w.get("note_files", 0.10) * min(note_files, 1))
    return {
        "mod_rate": mod_rate,
        "entropy_jump": entropy_jump,
        "high_entropy_ratio": high_entropy_ratio,
        "ext_change": ext_change,
        "note_files": note_files,
        "score": score,
        "with_base": with_base,
        "high": high,
    }
