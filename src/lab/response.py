"""Response actions on ransomware alert (spec Section 8)."""
from __future__ import annotations
from . import state as st
from .logging_setup import get_logger

def on_alert(cfg, features: dict, attack_start_iso: str, detected_at_iso: str, log_dir=None):
    log = get_logger("detector", log_dir=log_dir or cfg.log_dir, host=cfg.host)
    log.error("alert_raised", f"ransomware detected score={features.get('score',0):.2f}",
              score=features.get("score"), features=features,
              attack_start=attack_start_iso, detected_at=detected_at_iso)
    st.set_paused(cfg.state_db, True)
    try:
        cur = int(st.get_flag(cfg.state_db, "alerts_total", "0") or 0)
        st.set_flag(cfg.state_db, "alerts_total", str(cur + 1))
        st.set_flag(cfg.state_db, "detector_score", str(features.get("score", 0)))
    except Exception:
        pass
    n = st.mark_suspect_since(cfg.state_db, attack_start_iso, cfg.safety_margin_seconds)
    log.warning("backups_paused", f"backups paused; {n} snapshots marked suspect")
    try:
        from .exporter import inc_alert, set_detector_score, set_paused
        inc_alert()
        set_detector_score(features.get("score", 0))
        set_paused(True)
    except Exception:
        pass
    print(f"[ALERT] score={features.get('score',0):.2f} attack_start={attack_start_iso} suspect_marked={n}")
    print("Next: lab restore --latest-clean")
    return {"suspect_marked": n}
