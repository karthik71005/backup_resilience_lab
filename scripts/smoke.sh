#!/bin/bash
# Watchdog smoke test: burst-modify 60 text files with high-entropy content,
# then poll detector score kv. Run INSIDE agent container.
set -u
cd /data/victim/docs
for i in $(seq 0 59); do
  head -c 3000 /dev/urandom | base64 > smoke_$i.txt &
done
wait
echo "burst written"
sleep 12
python3 /tmp/db_helper.py score
