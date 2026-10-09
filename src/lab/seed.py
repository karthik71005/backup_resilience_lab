"""Sample-data generator: ~300 files/server, 70% text/csv/json, 20% zip-like, 10% jpg-like."""
from __future__ import annotations
import csv
import json
import os
import random
import string
import zipfile
from pathlib import Path

def _rand_text(rng: random.Random, words: int = 60) -> str:
    vocab = ["ledger", "invoice", "backup", "resilience", "snapshot", "vault", "customer", "ticket", "server", "report", "finance", "audit", "policy", "restore", "entropy"]
    return " ".join(rng.choice(vocab) for _ in range(words))

def seed_data(victim: str | Path, count: int = 300, seed: int = 42):
    vdir = Path(victim)
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / ".LAB_SAFE_TO_ENCRYPT").write_text("lab-safe\n")
    rng = random.Random(seed)
    (vdir / "finance").mkdir(exist_ok=True)
    (vdir / "docs").mkdir(exist_ok=True)
    (vdir / "media").mkdir(exist_ok=True)
    n_text = int(count * 0.7)
    n_zip = int(count * 0.2)
    n_jpg = count - n_text - n_zip
    for i in range(n_text):
        kind = rng.choice(["txt", "csv", "json"])
        if kind == "txt":
            (vdir / "docs" / f"doc_{i:03d}.txt").write_text(_rand_text(rng, 80) + "\n")
        elif kind == "csv":
            p = vdir / "finance" / f"ledger_{i:03d}.csv"
            with open(p, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["id", "account", "amount"])
                for r in range(20):
                    w.writerow([r, rng.choice(["acct-a", "acct-b", "acct-c"]), round(rng.uniform(1, 5000), 2)])
        else:
            p = vdir / "docs" / f"record_{i:03d}.json"
            p.write_text(json.dumps({"id": i, "note": _rand_text(rng, 20), "values": [rng.random() for _ in range(10)]}))
    for i in range(n_zip):
        p = vdir / "docs" / f"bundle_{i:03d}.zip"
        with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("inner.txt", _rand_text(rng, 200))
    for i in range(n_jpg):
        p = vdir / "media" / f"img_{i:03d}.jpg"
        p.write_bytes(os.urandom(20000))
    return {"dir": str(vdir), "count": count}
