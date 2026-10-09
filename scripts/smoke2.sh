#!/bin/bash
# Smoke test v2: OVERWRITE 60 existing txt files with random bytes over ~12s,
# then poll detector score kv. Run INSIDE agent container.
set -u
cd /data/victim/docs
for round in 1 2 3; do
  for f in doc_0*.txt; do
    head -c 3000 /dev/urandom | base64 > "$f" &
  done
  wait
  sleep 3
done
echo "overwrite burst done"
sleep 7
python3 /tmp/db_helper.py score
