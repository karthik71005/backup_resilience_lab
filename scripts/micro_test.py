"""Micro-test: overwrite+rename 5 files, dump what the handler saw."""
import os, sys, tempfile, time
sys.path.insert(0, "src")
os.environ["LAB_ALLOW_HOST_SIM"] = "1"
from lab.config import LabConfig
from lab.detector import Detector
from lab import state as st
from lab.features import file_entropy
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

tmp = tempfile.mkdtemp(prefix="micro-")
data = os.path.join(tmp, "data")
os.makedirs(data)
for i in range(5):
    Path(data, f"f{i}.txt").write_text("hello world plaintext " * 20)

cfg = LabConfig(host="micro", data_dir=data, victim_dir=data, log_dir=os.path.join(tmp, "log"),
                state_db=os.path.join(tmp, "s.db"))
for i in range(5):
    st.upsert_baseline(cfg.state_db, f"f{i}.txt", file_entropy(os.path.join(data, f"f{i}.txt")))

det = Detector(cfg)

class H(FileSystemEventHandler):
    def on_modified(self, e):
        if not e.is_directory:
            det.note_event(e.src_path, "modified")
    def on_moved(self, e):
        if not e.is_directory:
            det.note_event(e.dest_path, "moved")

obs = Observer()
obs.schedule(H(), data, recursive=True)
obs.start()
time.sleep(1)
# attack-like: overwrite with random then rename, fast
import secrets
for i in range(5):
    p = Path(data, f"f{i}.txt")
    p.write_bytes(secrets.token_bytes(3000))
    p.rename(Path(data, f"f{i}.txt.locked"))
time.sleep(3)
obs.stop()
obs.join()
for e in det.events:
    print(e["kind"], e["path"], "entropy_now=", round(e["entropy_now"], 2))
