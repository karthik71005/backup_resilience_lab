#!/bin/bash
# run_all.sh — start (or stop) the ENTIRE lab backend with one command.
#
#   bash scripts/run_all.sh          # start everything
#   bash scripts/run_all.sh down     # stop everything
#   bash scripts/run_all.sh status   # show status
#
# Does, in order:
#   1. preflight (docker daemon, repo root, .env exists)
#   2. docker compose up -d (all 7 services)
#   3. waits for storage + agents + prometheus + grafana
#   4. builds the React frontend if node exists and dist/ is missing
#   5. starts the FastAPI dashboard on :8090 (background, logs to /tmp/api.log)
# Idempotent: safe to re-run; already-running pieces are left alone.
set -u
cd "$(dirname "$0")/.."

API_PORT="${API_PORT:-8090}"

fail() { echo "ERROR: $1" >&2; exit 1; }

preflight() {
  docker version --format '{{.Server.Version}}' >/dev/null 2>&1 \
    || fail "docker daemon not reachable (start Docker Desktop, check WSL integration)"
  [ -f .env ] || { echo "no .env — copying from .env.example"; cp .env.example .env; }
  command -v python3 >/dev/null || fail "python3 missing"
}

wait_for() { # wait_for <url> <label> [tries]
  local url="$1" label="$2" tries="${3:-24}" i=0
  while [ $i -lt "$tries" ]; do
    if curl -sf -m 5 "$url" >/dev/null 2>&1; then echo "  [ok] $label"; return 0; fi
    sleep 5; i=$((i + 1))
  done
  echo "  [MISS] $label ($url)"; return 1
}

do_up() {
  preflight
  echo "== 1/4 compose up =="
  docker compose --env-file .env up -d || fail "compose up failed"
  echo "== 2/4 waiting for services =="
  wait_for http://localhost:9000/minio/health/live "storage :9000"
  wait_for http://localhost:8001/metrics "agent-1 metrics :8001"
  wait_for http://localhost:8002/metrics "agent-2 metrics :8002"
  wait_for http://localhost:9090/-/healthy "prometheus :9090"
  wait_for http://localhost:3000/api/health "grafana :3000"
  echo "== 3/4 frontend =="
  if [ -d dashboard/frontend/dist ]; then
    echo "  [ok] dist/ present"
  elif command -v node >/dev/null 2>&1; then
    echo "  building frontend…"
    (cd dashboard/frontend && npm ci --ignore-scripts >/dev/null 2>&1 && npm run build) \
      && echo "  [ok] built" || echo "  [MISS] frontend build failed (API still works, UI needs dist/)"
  else
    echo "  [skip] no node in WSL and no dist/ — API works, build UI with: cd dashboard/frontend && npm ci && npm run build"
  fi
  echo "== 4/4 dashboard API :$API_PORT =="
  if curl -sf -m 5 "http://localhost:$API_PORT/api/health" >/dev/null 2>&1; then
    echo "  [ok] already running"
  else
    setsid nohup python3 dashboard/api.py --port "$API_PORT" > /tmp/api.log 2>&1 < /dev/null &
    # first /api/health runs the full 9-service check; allow up to ~1 min
    ok=0
    for i in $(seq 1 6); do
      sleep 10
      if curl -sf -m 30 "http://localhost:$API_PORT/api/health" >/dev/null 2>&1; then ok=1; break; fi
    done
    if [ $ok -eq 1 ]; then
      echo "  [ok] started (log: /tmp/api.log)"
    else
      echo "  [MISS] api failed to start — see /tmp/api.log"; tail -5 /tmp/api.log; return 1
    fi
  fi
  echo
  echo "LAB IS UP:"
  echo "  console : http://localhost:$API_PORT   (API docs: /docs)"
  echo "  grafana : http://localhost:3000   prometheus: :9090   storage: :9001"
  echo "stop with: bash scripts/run_all.sh down"
}

do_down() {
  echo "stopping dashboard API…"
  pkill -f 'dashboard/api.py' 2>/dev/null
  pkill -f 'dashboard/app.py' 2>/dev/null
  echo "stopping compose stack (volumes kept)…"
  docker compose down
  echo "DOWN. Data kept in volumes; 'down -v' would delete it (don't, unless resetting)."
}

do_status() {
  docker compose ps --format 'table {{.Name}}\t{{.Status}}'
  curl -sf -m 5 "http://localhost:$API_PORT/api/health" >/dev/null 2>&1 \
    && echo "dashboard API :$API_PORT UP" || echo "dashboard API :$API_PORT down"
}

case "${1:-up}" in
  up) do_up ;;
  down) do_down ;;
  status) do_status ;;
  *) echo "usage: bash scripts/run_all.sh [up|down|status]"; exit 1 ;;
esac
