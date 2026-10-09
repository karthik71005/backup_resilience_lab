"""Debug: score a synthetic attack burst against REAL baselines in container."""
import sys
sys.path.insert(0, "/app/src")
from lab.config import load_config
from lab import state as st
from lab.features import compute_window_features

cfg = load_config()
bl = st.get_all_baselines(cfg.state_db)
print(f"baselines: {len(bl)}")
import statistics
vals = list(bl.values())
if vals:
    print(f"baseline entropy min={min(vals):.2f} median={statistics.median(vals):.2f} max={max(vals):.2f}")
    low = sum(1 for v in vals if v < cfg.entropy_baseline_low)
    print(f"below {cfg.entropy_baseline_low}: {low}/{len(vals)}")
# synthetic burst: 150 modified real paths with encrypted entropy
paths = list(bl.keys())[:150]
ev = [{"path": p, "kind": "modified", "entropy_now": 7.9, "ts": 0} for p in paths]
feats = compute_window_features(ev, bl, cfg)
print("synthetic-burst features:", {k: round(v, 3) if isinstance(v, float) else v for k, v in feats.items()})
print("would_alert:", feats["score"] >= cfg.score_threshold, "threshold:", cfg.score_threshold)
