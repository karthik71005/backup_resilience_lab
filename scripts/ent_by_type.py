"""Measure AES-CTR ciphertext entropy per seed file type."""
import os, sys, tempfile
sys.path.insert(0, "src")
from lab.seed import seed_data
from lab.simulator import encrypt_raw
from lab.features import file_entropy, shannon_entropy
from pathlib import Path
import secrets

tmp = tempfile.mkdtemp(prefix="ent-")
victim = os.path.join(tmp, "victim")
seed_data(victim, count=300)
key = secrets.token_bytes(32)
import collections
by_ext = collections.defaultdict(list)
for p in sorted(Path(victim).rglob("*")):
    if p.is_file() and p.name != ".LAB_SAFE_TO_ENCRYPT":
        raw = p.read_bytes()
        ct = encrypt_raw(key, raw)
        by_ext[p.suffix].append((len(raw), file_entropy(p), shannon_entropy(ct)))
for ext, vals in sorted(by_ext.items()):
    sizes = [v[0] for v in vals]
    bases = [v[1] for v in vals]
    cts = [v[2] for v in vals]
    print(f"{ext or '(none)'}: n={len(vals)} size_min={min(sizes)} size_med={sorted(sizes)[len(sizes)//2]} "
          f"base_min={min(bases):.2f} base_max={max(bases):.2f} ct_min={min(cts):.2f} ct_med={sorted(cts)[len(cts)//2]:.2f}")
