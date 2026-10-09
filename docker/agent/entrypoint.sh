#!/bin/bash
set -e
export LAB_HOST="${LAB_HOST:-$(hostname)}"
echo "[entrypoint] starting lab agent on $LAB_HOST"
mkdir -p /data/victim /var/log/lab /var/lib/lab /restore /cache
# Start exporter in background
python3 -m lab.cli exporter --port 8000 &
# Start detector in background
python3 -m lab.cli detector run &
# Start backup scheduler loop in background
python3 -m lab.cli backup loop &
wait
