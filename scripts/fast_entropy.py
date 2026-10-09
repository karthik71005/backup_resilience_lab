"""Fast focused measurement: encrypt+rename 100 files at full speed, histogram handler-seen entropy."""
import os, sys, tempfile, time, secrets
sys.path.insert(0, "src")
os.environ["LAB_ALLOW_HOST_SIM"] = "1"
from lab.config import LabConfig
from lab.detector import Detector
from lab import state as st
from lab.features import file_entropy
from lab.simulator import encrypt_raw
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

tmp = tempfile.mkdtemp(prefix="fast-")
data = os.path.join(tmp, "data")
os.makedirs(data)
for i in range(100):
    Path(data, f"f{i}.txt").write_text("hello world plaintext data " * 30)

cfg = LabConfig(host="fast", data_dir=data, victim_dir=data, log_dir=os.path.join(tmp, "log"),
                state_db=os.path.join(tmp, "s.db"))
for i in range(100):
    st.upsert_baseline(cfg.state_db, f"f{i}.txt", file_entropy(os.path.join(data, f"f{i}.txt")))

det = Detector(cfg)

class H(FileSystemEventHandler):
    def on_modified(self, e):
        if not e.is_directory:
            det.note_event(e.src_path, "modified")
    def on_moved(self, e):
        if not e.is_directory:
            det.note_event(e.dest_path, "moved", src=e.src_path)

obs = Observer(); obs.schedule(H(), data, recursive=True); obs.start()
time.sleep(0.5)
key = secrets.token_bytes(32)
for i in range(100):
    p = Path(data, f"f{i}.txt")
    p.write_bytes(encrypt_raw(key, p.read_bytes()))
    p.rename(Path(data, f"f{i}.txt.locked"))
time.sleep(4)
obs.stop(); obs.join()
from collections import Counter
mods = [e["entropy_now"] for e in det.events if e["kind"] == "modified"]
movs = [(e["entropy_now"], e["src"]) for e in det.events if e["kind"] == "moved"]
print(f"modified: n={len(mods)}")
h = Counter(round(v, 1) for v in mods)
for k in sorted(h): print(f"  ent={k}: {h[k]}")
print(f"moved: n={len(movs)} src_set={sum(1 for _, s in movs if s)}")
h2 = Counter(round(v, 1) for v, _ in movs)
for k in sorted(h2): print(f"  ent={k}: {h2[k]}")
bl = st.get_all_baselines(cfg.state_db)
print(f"baselines: {len(bl)} sample: {list(bl.items())[:2]}")
print(f"move src sample: {[s for _, s in movs[:3]]}")
