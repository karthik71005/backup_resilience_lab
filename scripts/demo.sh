#!/bin/bash
# End-to-end demo: attack -> detect -> restore, appends to docs/RESULTS.md (spec Section 9/14 Phase 5).
set -e
cd "$(dirname "$0")/.."
echo "=== Lab demo ==="
echo "[1/4] Seeding victim data (if empty)..."
docker compose exec app-server-1 python3 -m lab.cli seed --count 300 || true
echo "[2/4] Triggering guarded attack on app-server-1..."
docker compose exec app-server-1 python3 -m lab.cli attack run --rate 15 || true
echo "Waiting 25s for detector windows..."
sleep 25
echo "[3/4] Restoring latest clean snapshot..."
docker compose exec app-server-1 python3 -m lab.cli restore --latest-clean --host app-server-1 || true
echo "[4/4] Triage + case demo (inject dns_failure, analyze, clear)..."
docker compose exec app-server-1 python3 -m lab.cli backup run || true
echo "Demo complete. Check docs/RESULTS.md and cases/."
