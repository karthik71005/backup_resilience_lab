import tempfile, os
from lab.detector import Detector
from lab.config import LabConfig
from lab import state as st

def _mk_cfg(tmp):
    data = os.path.join(tmp, "data")
    os.makedirs(os.path.join(data, "victim"), exist_ok=True)
    # sentinel not needed for detector
    return LabConfig(host="test", data_dir=data, victim_dir=os.path.join(data, "victim"),
                     log_dir=os.path.join(tmp, "log"), state_db=os.path.join(tmp, "s.db"),
                     window_seconds=10, score_threshold=0.6, consecutive_windows=2)

def test_detector_alerts_on_burst(tmp_path):
    cfg = _mk_cfg(str(tmp_path))
    # baselines: low entropy text
    for i in range(40):
        st.upsert_baseline(cfg.state_db, f"f{i}", 4.0)
    d = Detector(cfg)
    # create real files with high entropy so file_entropy reads high
    for i in range(40):
        p = os.path.join(cfg.data_dir, f"f{i}")
        with open(p, "wb") as f:
            f.write(os.urandom(4000))
        d.note_event(p, "modified")
    # force entropy_now high (file_entropy of urandom may vary; override last events)
    for e in d.events:
        e["entropy_now"] = 7.9
    d.evaluate()
    alert = d.evaluate()  # 2nd consecutive window
    assert alert is not None
    assert alert["features"]["score"] >= 0.6
    assert st.is_paused(cfg.state_db)

def test_false_positive_jpg_bulk_copy(tmp_path):
    """High entropy files whose baseline is ALSO high should not alert (jpg-like)."""
    cfg = _mk_cfg(str(tmp_path))
    for i in range(30):
        st.upsert_baseline(cfg.state_db, f"img{i}.jpg", 7.8)
    d = Detector(cfg)
    for i in range(30):
        p = os.path.join(cfg.data_dir, f"img{i}.jpg")
        with open(p, "wb") as f:
            f.write(os.urandom(4000))
        d.note_event(p, "created")
    for e in d.events:
        e["entropy_now"] = 7.9
    d.evaluate()
    assert d.evaluate() is None  # no alert: high_entropy_ratio=0 since baseline already high

def test_false_positive_single_zip(tmp_path):
    cfg = _mk_cfg(str(tmp_path))
    st.upsert_baseline(cfg.state_db, "bundle.zip", 7.6)
    d = Detector(cfg)
    p = os.path.join(cfg.data_dir, "bundle.zip")
    with open(p, "wb") as f:
        f.write(os.urandom(4000))
    d.note_event(p, "modified")
    for e in d.events:
        e["entropy_now"] = 7.7
    d.evaluate()
    assert d.evaluate() is None

def test_false_positive_normal_edits(tmp_path):
    cfg = _mk_cfg(str(tmp_path))
    st.upsert_baseline(cfg.state_db, "a.txt", 4.0)
    d = Detector(cfg)
    p = os.path.join(cfg.data_dir, "a.txt")
    with open(p, "w") as f:
        f.write("hello world")
    d.note_event(p, "modified")
    for e in d.events:
        e["entropy_now"] = 4.1
    d.evaluate()
    assert d.evaluate() is None
