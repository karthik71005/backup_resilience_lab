"""Host-side helper: read last alert from a detector log copy. Usage: parse_alert.py <logfile>"""
import json
import sys

last = None
with open(sys.argv[1]) as f:
    for line in f:
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") == "alert_raised":
            last = r
if last:
    print(last["detected_at"], last["attack_start"], round(last.get("score", 0), 3))
else:
    print("NO ALERT")
