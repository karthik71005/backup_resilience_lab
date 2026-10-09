"""Inotify-based detector with sliding window scoring (spec Section 8)."""
from __future__ import annotations
import hashlib
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .features import file_entropy, compute_window_features
from .logging_setup import get_logger
from . import state as st

KNOWN_EXTS_KEY = "known_exts"

def _known_exts(db_path) -> set:
    v = st.get_flag(db_path, KNOWN_EXTS_KEY, "")
    return set(x for x in v.split(",") if x)

def _save_known_exts(db_path, exts: set):
    st.set_flag(db_path, KNOWN_EXTS_KEY, ",".join(sorted(exts)))

class Detector:
    def __init__(self, cfg=None):
        self.cfg = cfg or load_config()
        self.log = get_logger("detector", log_dir=self.cfg.log_dir, host=self.cfg.host)
        self.events: deque = deque()
        self.hot_windows = 0
        self.alerted = False
        # seed known extensions from baseline scan
        root = Path(self.cfg.data_dir)
        exts = {p.suffix.lower() for p in root.rglob("*") if p.is_file() and p.suffix}
        existing = _known_exts(self.cfg.state_db)
        _save_known_exts(self.cfg.state_db, existing | exts)

    def note_event(self, path: str, kind: str, content_hash: str | None = None, src: str | None = None):
        now = time.time()
        full = Path(path) if Path(path).is_absolute() else Path(self.cfg.data_dir) / path
        try:
            rel = str(full.relative_to(self.cfg.data_dir))
        except ValueError:
            rel = str(path)
        ent_now = file_entropy(full) if full.exists() and full.is_file() else 0.0
        src_rel = None
        if src:
            sfull = Path(src) if Path(src).is_absolute() else Path(self.cfg.data_dir) / src
            try:
                src_rel = str(sfull.relative_to(self.cfg.data_dir))
            except ValueError:
                src_rel = str(src)
        new_ext_unseen = False
        if kind == "moved":
            ext = Path(rel).suffix.lower()
            known = _known_exts(self.cfg.state_db)
            if ext and ext not in known:
                new_ext_unseen = True
                known.add(ext)
                _save_known_exts(self.cfg.state_db, known)
        self.events.append({"path": rel, "kind": kind, "entropy_now": ent_now,
                            "content_hash": content_hash, "new_ext_unseen": new_ext_unseen,
                            "src": src_rel, "ts": now})

    def evaluate(self) -> dict | None:
        """Evaluate current window; return alert info if threshold crossed N consecutive windows."""
        now = time.time()
        cutoff = now - self.cfg.window_seconds
        window = [e for e in self.events if e["ts"] >= cutoff]
        # prune old
        while self.events and self.events[0]["ts"] < cutoff - self.cfg.window_seconds:
            self.events.popleft()
        baselines = st.get_all_baselines(self.cfg.state_db)
        feats = compute_window_features(window, baselines, self.cfg)
        try:
            st.set_flag(self.cfg.state_db, "detector_score", str(feats["score"]))
        except Exception:
            pass
        try:
            from .exporter import set_detector_score
            set_detector_score(feats["score"])
        except Exception:
            pass
        if feats["score"] >= self.cfg.score_threshold:
            self.hot_windows += 1
        else:
            self.hot_windows = 0
        if self.hot_windows >= self.cfg.consecutive_windows and not self.alerted:
            self.alerted = True
            earliest = min((e["ts"] for e in window), default=now)
            attack_start = datetime.fromtimestamp(earliest, tz=timezone.utc).isoformat()
            detected_at = datetime.now(timezone.utc).isoformat()
            from .response import on_alert
            on_alert(self.cfg, feats, attack_start, detected_at)
            return {"features": feats, "attack_start": attack_start, "detected_at": detected_at}
        return None

    def run(self):
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        det = self

        class H(FileSystemEventHandler):
            def _hash_small(self, p):
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
                    det.note_event(e.src_path, "created", self._hash_small(e.src_path))
            def on_moved(self, e):
                if not e.is_directory:
                    det.note_event(e.dest_path, "moved", src=e.src_path)
            def on_deleted(self, e):
                if not e.is_directory:
                    det.note_event(e.src_path, "deleted")

        obs = Observer()
        Path(self.cfg.data_dir).mkdir(parents=True, exist_ok=True)
        obs.schedule(H(), self.cfg.data_dir, recursive=True)
        obs.start()
        self.log.info("detector_start", f"watching {self.cfg.data_dir} window={self.cfg.window_seconds}s threshold={self.cfg.score_threshold}")
        try:
            while True:
                time.sleep(self.cfg.window_seconds / 2)
                self.evaluate()
        except KeyboardInterrupt:
            pass
        finally:
            obs.stop(); obs.join()


def tune(cfg=None) -> dict:
    """Replay synthetic scenarios (burst + 3 false-positives) and report precision/recall."""
    from .features import compute_window_features
    cfg = cfg or load_config()
    scenarios = []
    # True positive: burst of 40 high-entropy jumps + unseen ext
    base = {f"f{i}": 4.0 for i in range(40)}
    ev = [{"path": f"f{i}", "kind": "modified", "entropy_now": 7.9, "ts": 0} for i in range(40)]
    ev += [{"path": f"r{i}.locked", "kind": "moved", "entropy_now": 7.9, "new_ext_unseen": True, "ts": 0} for i in range(10)]
    scenarios.append(("ransomware_burst", True, compute_window_features(ev, base, cfg)["score"] >= cfg.score_threshold))
    # FP1: normal low-rate text edits
    scenarios.append(("normal_edits", False,
                      compute_window_features([{"path": "a.txt", "kind": "modified", "entropy_now": 4.1, "ts": 0}],
                                              {"a.txt": 4.0}, cfg)["score"] >= cfg.score_threshold))
    # FP2: bulk jpg copy (baseline already high)
    jb = {f"img{i}.jpg": 7.8 for i in range(30)}
    je = [{"path": f"img{i}.jpg", "kind": "created", "entropy_now": 7.9, "ts": 0} for i in range(30)]
    scenarios.append(("jpg_bulk_copy", False, compute_window_features(je, jb, cfg)["score"] >= cfg.score_threshold))
    # FP3: single zip rewrite
    scenarios.append(("single_zip", False,
                      compute_window_features([{"path": "b.zip", "kind": "modified", "entropy_now": 7.7, "ts": 0}],
                                              {"b.zip": 7.6}, cfg)["score"] >= cfg.score_threshold))
    tp = sum(1 for _, want, got in scenarios if want and got)
    fp = sum(1 for _, want, got in scenarios if not want and got)
    fn = sum(1 for _, want, got in scenarios if want and not got)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return {"threshold": cfg.score_threshold, "window": cfg.window_seconds, "weights": cfg.weights,
            "scenarios": [{"name": n, "is_attack": w, "alerted": g} for n, w, g in scenarios],
            "precision": round(precision, 3), "recall": round(recall, 3)}
