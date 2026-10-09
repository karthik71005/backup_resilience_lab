"""Local full-chain repro: real Observer + real simulator + real scoring."""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, "src")
os.environ["LAB_ALLOW_HOST_SIM"] = "1"

from lab.config import LabConfig
from lab.seed import seed_data
from lab.detector import Detector
from lab import state as st

tmp = tempfile.mkdtemp(prefix="repro-")
data = os.path.join(tmp, "data")
victim = os.path.join(data, "victim")
logd = os.path.join(tmp, "log")
db = os.path.join(tmp, "s.db")
seed_data(victim, count=300)

cfg = LabConfig(host="repro", data_dir=data, victim_dir=victim, log_dir=logd,
                state_db=db, window_seconds=10, score_threshold=0.55,
                consecutive_windows=2)
# baselines like a clean backup would
from lab.features import file_entropy
from pathlib import Path
for p in sorted(Path(data).rglob("*")):
    if p.is_file():
        st.upsert_baseline(db, str(p.relative_to(data)), file_entropy(p))

det = Detector(cfg)

# watchdog observer in background thread (same as Detector.run but manual stepping)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import hashlib

class H(FileSystemEventHandler):
    def _h(self, p):
        try:
            with open(p, "rb") as f:
                return hashlib.sha256(f.read(4096)).hexdigest()
        except Exception:
            return None
    def on_modified(self, e):
        if not e.is_directory:
            det.note_event(e.src_path, "modified")
    def on_created(self, e):
        if not e.is_directory:
            det.note_event(e.src_path, "created", self._h(e.src_path))
    def on_moved(self, e):
        if not e.is_directory:
            det.note_event(e.dest_path, "moved", src=e.src_path)
    def on_deleted(self, e):
        if not e.is_directory:
            det.note_event(e.src_path, "deleted")

obs = Observer()
obs.schedule(H(), data, recursive=True)
obs.start()

from lab.simulator import run_attack
t = threading.Thread(target=lambda: run_attack(cfg, rate=15.0, delay=1.0), daemon=True)
t0 = time.time()
t.start()
alert = None
while time.time() - t0 < 45:
    time.sleep(2)
    r = det.evaluate()
    n = len(det.events)
    from lab.features import compute_window_features
    from lab import state as _st
    _w = [e for e in det.events if e["ts"] >= time.time() - cfg.window_seconds]
    _f = compute_window_features(_w, _st.get_all_baselines(db), cfg)
    print(f"t={time.time()-t0:4.1f}s n={n} hot={det.hot_windows} alert={bool(r)} "
          f"mod={_f['mod_rate']} hir={_f['high_entropy_ratio']:.2f} ext={_f['ext_change']} score={_f['score']:.3f} "
          f"wb={_f.get('with_base')} high={_f.get('high')}", flush=True)
    if r:
        alert = r
        break
obs.stop()
obs.join()
print("ALERT:" if alert else "NO ALERT", alert["features"] if alert else "")
