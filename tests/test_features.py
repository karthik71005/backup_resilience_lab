import math
from lab.features import shannon_entropy, file_entropy, compute_window_features
from lab.config import LabConfig

def test_entropy_known():
    assert shannon_entropy(b"") == 0.0
    assert shannon_entropy(b"aaaa") == 0.0
    # uniform 2 symbols -> 1 bit
    assert abs(shannon_entropy(b"abababab") - 1.0) < 0.01
    # uniform 256 symbols -> 8 bits
    data = bytes(range(256)) * 4
    assert abs(shannon_entropy(data) - 8.0) < 0.01

def test_entropy_text_vs_random(tmp_path):
    import os
    low = tmp_path / "low.txt"
    low.write_text("hello world " * 500)
    high = tmp_path / "high.bin"
    high.write_bytes(os.urandom(8000))
    assert file_entropy(low) < 5.0
    assert file_entropy(high) > 7.0

def _cfg():
    return LabConfig()

def test_window_burst_scores_high():
    cfg = _cfg()
    baselines = {f"f{i}": 4.0 for i in range(40)}
    events = [{"path": f"f{i}", "kind": "modified", "entropy_now": 7.9, "ts": 0} for i in range(40)]
    feats = compute_window_features(events, baselines, cfg)
    assert feats["mod_rate"] == 40
    assert feats["high_entropy_ratio"] == 1.0
    assert feats["score"] >= cfg.score_threshold

def test_window_normal_edits_low():
    cfg = _cfg()
    baselines = {"a.txt": 4.0, "b.txt": 4.2}
    events = [{"path": "a.txt", "kind": "modified", "entropy_now": 4.1, "ts": 0}]
    feats = compute_window_features(events, baselines, cfg)
    assert feats["score"] < cfg.score_threshold
