from lab.features import compute_window_features
from lab.config import LabConfig

def test_rename_storm_does_not_dilute_ratio():
    """Regression (Oct 2026): real attacks overwrite AND rename to .locked.
    Race-accurate shape: stale modified events read entropy 0.0 (file already
    renamed when the handler runs); moved events carry entropy 7.9 and link
    back to the source path for baseline lookup. Must still alert."""
    cfg = LabConfig(score_threshold=0.55)
    base = {f"doc_{i:03d}.txt": 4.0 for i in range(210)}
    base.update({f"bundle_{i:03d}.zip": 7.6 for i in range(60)})
    base.update({f"img_{i:03d}.jpg": 7.8 for i in range(30)})
    ev = []
    for i in range(210):
        ev.append({"path": f"doc_{i:03d}.txt", "kind": "modified", "entropy_now": 0.0, "ts": 0})
        ev.append({"path": f"doc_{i:03d}.txt.locked", "kind": "moved", "entropy_now": 7.9,
                   "src": f"doc_{i:03d}.txt", "new_ext_unseen": (i == 0), "ts": 0})
    for i in range(60):
        ev.append({"path": f"bundle_{i:03d}.zip", "kind": "modified", "entropy_now": 0.0, "ts": 0})
        ev.append({"path": f"bundle_{i:03d}.zip.locked", "kind": "moved", "entropy_now": 7.9,
                   "src": f"bundle_{i:03d}.zip", "new_ext_unseen": False, "ts": 0})
    for i in range(30):
        ev.append({"path": f"img_{i:03d}.jpg", "kind": "modified", "entropy_now": 0.0, "ts": 0})
        ev.append({"path": f"img_{i:03d}.jpg.locked", "kind": "moved", "entropy_now": 7.9,
                   "src": f"img_{i:03d}.jpg", "new_ext_unseen": False, "ts": 0})
    feats = compute_window_features(ev, base, cfg)
    assert feats["score"] >= cfg.score_threshold, feats
