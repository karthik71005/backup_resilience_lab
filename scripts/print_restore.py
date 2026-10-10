"""Print restore summary line. Usage: print_restore.py <jsonfile>"""
import json
import sys

r = json.load(open(sys.argv[1]))
v = r["verify"]
print(r["snapshot_id"][:8], v["ok"], v["total"], r["rto_s"], r["rpo_s"], r["detection_latency_s"])
