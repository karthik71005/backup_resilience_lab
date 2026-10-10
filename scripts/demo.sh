#!/bin/bash
# End-to-end demo (5 min): healthy backup -> vault proof -> attack/detect ->
# restore/verify -> fault/triage/case. Every step verified Oct 2026, see docs/RESULTS.md.
set -u
cd "$(dirname "$0")/.."

echo "=== [1/5] Stack + seed + clean backup ==="
docker compose --env-file .env up -d
docker compose exec app-server-1 python3 -m lab.cli seed --count 300
sleep 15  # let reseed burst age out of detector windows
docker compose exec app-server-1 python3 -m lab.cli backup run

echo "=== [2/5] Vault immutability ==="
docker compose exec app-server-1 python3 -m lab.cli vault status
docker compose exec app-server-1 python3 -m lab.cli vault try-delete  # must be refused (AccessDenied)

echo "=== [3/5] Attack -> detect (watch score, alert, pause) ==="
docker compose exec app-server-1 python3 -m lab.cli attack run --rate 15
sleep 8
docker compose exec app-server-1 grep alert_raised /var/log/lab/detector.jsonl | tail -1
curl -s http://localhost:8001/metrics | grep -E 'lab_alerts_total|lab_backups_paused' | grep -v '#'

echo "=== [4/5] Restore latest clean + verify ==="
docker compose exec app-server-1 python3 -m lab.cli restore --latest-clean --host app-server-1

echo "=== [5/5] Fault -> triage -> case (dns_failure example) ==="
docker compose exec app-server-1 python3 -m lab.cli fault inject dns_failure
docker network disconnect backup-resilience-lab_lab-net backup-resilience-lab-app-server-1-1
docker compose exec app-server-1 python3 -m lab.cli backup run || true
docker compose exec app-server-1 tail -5 /var/log/lab/backup.jsonl > /tmp/lab_demo_fail.jsonl
PYTHONPATH=src python3 -m lab.cli triage analyze /tmp/lab_demo_fail.jsonl
PYTHONPATH=src python3 -m lab.cli case create /tmp/lab_demo_fail.jsonl
docker network connect backup-resilience-lab_lab-net backup-resilience-lab-app-server-1-1
docker compose exec app-server-1 python3 -m lab.cli fault clear dns_failure
docker compose exec app-server-1 python3 -m lab.cli backup run
echo "Demo complete. Grafana: http://localhost:3000  Prometheus: http://localhost:9090"
echo "NOTE: after the attack segment backups are PAUSED by design; when done demonstrating, run:"
echo "  docker compose exec app-server-1 python3 -m lab.cli backup resume"
