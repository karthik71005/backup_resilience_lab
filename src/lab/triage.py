"""Triage: classify failure logs with YAML rules (spec Section 12)."""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import yaml

def load_rules(path: str | Path = "config/triage_rules.yaml") -> list[dict]:
    # try several locations
    cands = [Path(path), Path(__file__).resolve().parents[2] / "config" / "triage_rules.yaml",
             Path("config/triage_rules.yaml")]
    for c in cands:
        if c.exists():
            return yaml.safe_load(c.read_text()) or []
    raise FileNotFoundError(f"rules file not found (tried {cands})")

def _read_records(logfile: str | Path, since_hours: float | None = None) -> list[dict]:
    recs = []
    cutoff = None
    if since_hours:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    with open(logfile) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                r = {"message": line, "raw": line}
            if cutoff and r.get("ts"):
                try:
                    ts = datetime.fromisoformat(str(r["ts"]).replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except Exception:
                    pass
            recs.append(r)
    return recs

def classify_record(rec: dict, rules: list[dict]) -> dict | None:
    text = f"{rec.get('message','')} {rec.get('raw','')} {rec.get('event','')}"
    best, best_hits = None, -1
    for r in rules:
        if r.get("id") == "UNKNOWN":
            continue
        pats = r.get("match", [])
        hits = 0
        for p in pats:
            try:
                if re.search(p, text, re.IGNORECASE):
                    hits += 1
            except re.error:
                if p.lower() in text.lower():
                    hits += 1
        if hits > 0:
            # most matched patterns wins; tie -> higher severity (P1 > P2 > ...)
            sev_rank = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}.get(r.get("severity", "P3"), 9)
            cur_rank = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}.get((best or {}).get("severity", "P3"), 9)
            if hits > best_hits or (hits == best_hits and sev_rank < cur_rank):
                best, best_hits = r, hits
    if best is None:
        unk = next((r for r in rules if r.get("id") == "UNKNOWN"), None)
        return unk
    return best

def analyze(logfile: str, since: str | None = None, rules_path: str = "config/triage_rules.yaml") -> dict:
    rules = load_rules(rules_path)
    hours = None
    if since:
        m = re.match(r"(\d+)(h|m)?", since)
        if m:
            v = int(m.group(1))
            hours = v if (m.group(2) or "h") == "h" else v / 60
    recs = _read_records(logfile, hours)
    fails = [r for r in recs if r.get("level") in ("ERROR", "WARNING") or r.get("event") in ("backup_failed", "alert_raised")]
    if not fails:
        fails = recs[-20:]
    groups: dict[str, dict] = {}
    for r in fails:
        rule = classify_record(r, rules) or {"id": "UNKNOWN", "category": "unknown", "severity": "P3"}
        gid = rule["id"]
        g = groups.setdefault(gid, {"rule": rule, "count": 0, "first": None, "last": None, "samples": [], "hosts": set()})
        g["count"] += 1
        if r.get("ts"):
            g["first"] = g["first"] or r["ts"]
            g["last"] = r["ts"]
        if len(g["samples"]) < 3:
            g["samples"].append(r.get("raw") or r.get("message"))
        if r.get("host"):
            g["hosts"].add(r["host"])
    for g in groups.values():
        g["hosts"] = sorted(g["hosts"])
    return {"logfile": logfile, "records": len(recs), "failures": len(fails), "groups": groups}
