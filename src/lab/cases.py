"""Support case generation (spec Section 12)."""
from __future__ import annotations
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import state as st

def _restic_version() -> str:
    try:
        p = subprocess.run(["restic", "version"], capture_output=True, text=True, timeout=5)
        return (p.stdout or p.stderr or "").strip().splitlines()[0][:120]
    except Exception:
        return "unknown"

def create_case(analysis: dict, out_dir: str | Path = "cases", db_path: str | None = None, cfg=None) -> list[dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    existing = sorted(out.glob("CASE-*.json"))
    n = len(existing) + 1
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    created = []
    for gid, g in analysis["groups"].items():
        rule = g["rule"]
        cid = f"CASE-{day}-{n:03d}"
        n += 1
        case = {
            "id": cid,
            "title": f"{rule.get('category','unknown').upper()}: {rule.get('cause','failure')} ({gid})",
            "severity": rule.get("severity", "P3"),
            "category": rule.get("category", "unknown"),
            "rule_id": gid,
            "affected_host": ", ".join(g.get("hosts", [])) or "unknown",
            "first_occurrence": g.get("first"),
            "last_occurrence": g.get("last"),
            "occurrence_count": g.get("count"),
            "environment": {
                "os": platform.platform(),
                "restic": _restic_version(),
                "image": "backup-resilience-lab/agent:1.0",
            },
            "symptom": g.get("samples", [])[:3],
            "checks_performed": rule.get("checks", []),
            "probable_cause": rule.get("cause"),
            "recommended_fix": rule.get("fix"),
            "escalation_route": rule.get("route"),
            "status": "open",
            "customer_update": f"We detected {g.get('count')} occurrence(s) of {rule.get('cause','an issue')} on {', '.join(g.get('hosts', [])) or 'the host'}. Our team is applying the documented fix and will confirm the next successful backup. No action is needed from you right now.",
            "source_log": analysis.get("logfile"),
        }
        (out / f"{cid}.json").write_text(json.dumps(case, indent=2))
        md = f"""# {cid}: {case['title']}

- Severity: {case['severity']}
- Category: {case['category']} (rule {gid})
- Host: {case['affected_host']}
- First: {case['first_occurrence']} Last: {case['last_occurrence']} Count: {case['occurrence_count']}
- Status: open
- Route: {case['escalation_route']}

## Environment
- OS: {case['environment']['os']}
- Restic: {case['environment']['restic']}

## Symptom (verbatim)
```
{(chr(10).join(str(s)[:1000] for s in case['symptom']))}
```

## Checks
{chr(10).join('- ' + c for c in case['checks_performed'])}

## Probable cause
{case['probable_cause']}

## Recommended fix
{case['recommended_fix']}

## Customer update
{case['customer_update']}
"""
        (out / f"{cid}.md").write_text(md)
        if db_path:
            try:
                st.index_case(db_path, cid, case["title"], case["severity"], case["category"], case["affected_host"], str(out / f"{cid}.md"))
            except Exception:
                pass
        created.append(case)
    return created
