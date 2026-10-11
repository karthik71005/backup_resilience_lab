#!/bin/bash
cd ~/projects/backup-resilience-lab
pkill -f 'dashboard/api.py' 2>/dev/null
sleep 2
setsid nohup python3 dashboard/api.py --port 8090 > /tmp/api.log 2>&1 < /dev/null &
sleep 8
curl -s -m 30 http://localhost:8090/api/health | head -c 150
echo
echo APIDONE
