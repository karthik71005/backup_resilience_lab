"""Replicate repro mix (subdirs, mixed types, rate limit) and dump non-high identities."""
import os, sys, tempfile, time, threading
sys.path.insert(0, "src")
os.environ["LAB_ALLOW_HOST_SIM"] = "1"
from lab.config import LabConfig
from lab.seed import seed_data
from lab.detector import Detector
from lab import state as st
from lab.features import file_entropy, compute_window_features
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

tmp = tempfile.mkdtemp(prefix="mix-")
data = os.path.join(tmp, "data")
victim = os.path.join(data, "victim")
seed_data(victim, count=300)
cfg = LabConfig(host="mix", data_dir=data, victim_dir=victim, log_dir=os.path.join(tmp, "log"),
                state_db=os.path.join(tmp, "s.db"), window_seconds=10, score_threshold=0.55)
for p in sorted(Path(data).rglob("*")):
    if p.is_file():
        st.upsert_baseline(cfg.state_db, str(p.relative_to(data)), file_entropy(p))
bl = st.get_all_baselines(cfg.state_db)
print(f"baselines={len(bl)}")

det = Detector(cfg)
class H(FileSystemEventHandler):
    def on_modified(self, e):
        if not e.is_directory: det.note_event(e.src_path, "modified")
    def on_created(self, e):
        if not e.is_directory: det.note_event(e.src_path, "created")
    def on_moved(self, e):
        if not e.is_directory: det.note_event(e.dest_path, "moved", src=e.src_path)
obs = Observer(); obs.schedule(H(), data, recursive=True); obs.start()

from lab.simulator import run_attack
t = threading.Thread(target=lambda: run_attack(cfg, rate=15.0, delay=1.0), daemon=True)
t.start()
time.sleep(14)  # mid-attack
obs.stop(); obs.join()
win = [e for e in det.events if e["ts"] >= time.time() - 10]
print(f"window events={len(win)}")
moves = [e for e in win if e["kind"] == "moved"]
print(f"moves={len(moves)} with_src={sum(1 for e in moves if e.get('src'))}")
# sample move srcs vs baseline keys
for e in moves[:3]:
    print(f"  move src={e.get('src')!r} ent={e['entropy_now']:.2f} base={bl.get(e.get('src'))}")
noident = sum(1 for e in moves if e.get("src") not in bl)
print(f"moves whose src NOT in baselines: {noident}/{len(moves)}")
feats = compute_window_features(win, bl, cfg)
print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in feats.items()})
