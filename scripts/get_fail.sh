#!/bin/bash
# Extract last backup_failed line for a host. Usage: get_fail.sh <host> <outfile>
cd ~/projects/backup-resilience-lab
docker compose exec app-server-1 grep '"host": "'$1'"' /var/log/lab/backup.jsonl | grep backup_failed | tail -1 > $2
cat $2 | head -c 800
echo
