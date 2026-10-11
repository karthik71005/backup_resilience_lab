# Manual Setup & Run Guide (Windows 11 + WSL2)

Follow this top to bottom. Every step shows the exact command and what
success looks like. Estimated time: ~45 min first run (mostly downloads).

---

## 0. What you need

- Windows 10/11 with virtualization enabled in BIOS/UEFI
- 8 GB RAM minimum (16 GB comfortable), 20 GB free disk
- Admin rights on Windows (for WSL install)

Ports the lab uses — make sure nothing else listens on them:
`9000`, `9001` (storage), `9090` (Prometheus), `3000` (Grafana),
`8001`, `8002` (agent metrics). On Windows PowerShell:
`netstat -ano | findstr "9000 9001 9090 3000"`.

---

## 1. Install WSL2 + Ubuntu (PowerShell as Administrator)

```powershell
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
```

Reboot if asked, then open the **Ubuntu** app and create your Linux
username/password.

Optional: cap WSL memory so Docker doesn't eat Windows. Save as
`C:\Users\<you>\.wslconfig`, then run `wsl --shutdown`:

```ini
[wsl2]
memory=6GB
processors=4
swap=2GB
```

## 2. Install Windows apps (all normal installers)

1. **Docker Desktop** — during/after install go to
   Settings → General → enable **"Use the WSL 2 based engine"**,
   Settings → Resources → WSL Integration → enable **Ubuntu-24.04**.
2. **Git for Windows** (defaults are fine).
3. **VS Code** + the **WSL** extension (lets you open the Linux repo).

## 3. Verify inside the Ubuntu terminal

```bash
docker version          # expect Server 29.x
docker compose version  # expect v5.x
python3 --version       # 3.11+
git --version
```

If `docker` says "could not be found", wait 1–2 min (integration starts
slowly after `wsl --shutdown`) and retry. Do NOT run `wsl --shutdown`
repeatedly — it kills Docker's own distro and you wait again.

## 4. Get the repo (inside Ubuntu, Linux filesystem!)

> Keep the repo under `~`, NEVER under `/mnt/c` — file watching breaks
> and everything is slow there.

```bash
mkdir -p ~/projects && cd ~/projects
git clone <your-repo-url> backup-resilience-lab
cd backup-resilience-lab
cp .env.example .env
cat .env   # check MINIO_ROOT_USER/PASSWORD, RESTIC_PASSWORD exist
```

## 5. Build the agent image (takes ~3–5 min first time)

```bash
docker compose build
```

**Known issue:** if it fails with `error getting credentials ...`,
Docker Desktop's credential helper is flaking inside WSL. Workaround:

```bash
mkdir -p /tmp/dockercfg && echo '{}' > /tmp/dockercfg/config.json
DOCKER_CONFIG=/tmp/dockercfg docker compose build
```

## 6. Start the whole lab

```bash
docker compose --env-file .env up -d
sleep 30
docker compose ps
```

Expect 7 containers: `minio` (healthy), `minio-init` (exited 0),
`vault-sync`, `app-server-1`, `app-server-2`, `prometheus`, `grafana`.

Check each layer:

```bash
curl -s http://localhost:9000/minio/health/live   # {"status":"ok",...}
curl -s http://localhost:8001/metrics | grep -c lab_   # > 0
curl -s http://localhost:8002/metrics | grep -c lab_   # > 0
curl -s http://localhost:9090/-/healthy               # Prometheus Server is Healthy.
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/api/health  # 200
```

Open in a Windows browser: Grafana http://localhost:3000 (anon view works),
Prometheus http://localhost:9090, storage console http://localhost:9001.

## 7. Python tooling for host-side commands (triage/cases/tests)

The containers run the lab; your Ubuntu shell runs triage + tests:

```bash
pip3 install --break-system-packages -r requirements.txt
PYTHONPATH=src python3 -m pytest tests/ -q   # expect: 15 passed
```

## 8. Seed data + first backup (app-server-1)

```bash
docker compose exec app-server-1 python3 -m lab.cli seed --count 300
# {"dir": "/data/victim", "count": 300}
sleep 15   # let the reseed burst age out of detector windows
docker compose exec app-server-1 python3 -m lab.cli backup run
# {"ok": true, "snapshot_id": "...", "files": 301, ...}
```

Do the same seed on app-server-2 if you want both populated.

## 9. Prove the immutable vault

```bash
docker compose exec app-server-1 python3 -m lab.cli vault status
# objects growing, lock GOVERNANCE 1d, versioning Enabled
docker compose exec app-server-1 python3 -m lab.cli vault try-delete
# "ok": false, "refused": true, "message": "AccessDenied ... under GOVERNANCE retention"
```

If it says "vault empty", wait ~60 s (vault-sync interval) and retry.

## 10. Attack → detect → respond

```bash
docker compose exec app-server-1 python3 -m lab.cli attack run --rate 15
# takes ~25 s, prints run_id + attack_start/attack_end
sleep 10
docker compose exec app-server-1 grep alert_raised /var/log/lab/detector.jsonl | tail -1
```

Expect an `alert_raised` line with `score` ~0.6 and `attack_start`
matching the attack output within a second. Detection latency
(`detected_at - attack_start`) is typically 6–10 s. Also check:

```bash
curl -s http://localhost:8001/metrics | grep -E 'lab_alerts_total|lab_backups_paused' | grep -v '#'
# lab_alerts_total 1+, lab_backups_paused 1  (backups auto-paused)
docker compose exec app-server-1 python3 -m lab.cli backup run
# {"skipped": true}   <-- paused, correct
```

## 11. Restore the last clean snapshot

```bash
docker compose exec app-server-1 python3 -m lab.cli restore --latest-clean --host app-server-1
```

Expect `"ok": 301, "success_pct": 100.0` plus `rto_s`, `rpo_s`,
`detection_latency_s`. Copy the numbers into `docs/RESULTS.md`
(one row per run — 5 runs is the project's evidence).

Resume normal backups when done:

```bash
docker compose exec app-server-1 python3 -m lab.cli backup resume
```

## 12. Fault injection → triage → case (repeat per fault)

Full matrix (each: inject → failing backup → triage → case → clear →
healthy backup):

```bash
# 1. disk_full
docker compose exec app-server-1 python3 -m lab.cli fault inject disk_full
docker compose exec app-server-1 python3 -m lab.cli backup run   # exit 28, no space left
docker compose exec app-server-1 tail -3 /var/log/lab/backup.jsonl > /tmp/f.jsonl
PYTHONPATH=src python3 -m lab.cli triage analyze /tmp/f.jsonl   # STORAGE_DISK_FULL, P2
PYTHONPATH=src python3 -m lab.cli case create /tmp/f.jsonl      # CASE-*.md in cases/
docker compose exec app-server-1 python3 -m lab.cli fault clear disk_full

# 2. dns_failure (needs host step on Docker Desktop)
docker compose exec app-server-1 python3 -m lab.cli fault inject dns_failure
docker network disconnect backup-resilience-lab_lab-net backup-resilience-lab-app-server-1-1
docker compose exec app-server-1 python3 -m lab.cli backup run   # lookup failure
# ... triage (DNS_FAILURE P2) + case as above ...
docker network connect backup-resilience-lab_lab-net backup-resilience-lab-app-server-1-1
docker compose exec app-server-1 python3 -m lab.cli fault clear dns_failure

# 3. port_blocked
docker compose exec app-server-1 python3 -m lab.cli fault inject port_blocked
docker compose exec app-server-1 python3 -m lab.cli backup run   # i/o timeout
# ... triage (NETWORK_PORT_BLOCKED P2) + case ...
docker compose exec app-server-1 python3 -m lab.cli fault clear port_blocked

# 4. permission_denied
docker compose exec app-server-1 python3 -m lab.cli fault inject permission_denied
docker compose exec app-server-1 python3 -m lab.cli backup run   # exit 3, permission denied: victim/finance
# ... triage (PERMISSIONS P2) + case ...
docker compose exec app-server-1 python3 -m lab.cli fault clear permission_denied

# 5. bad_credentials
docker compose exec app-server-1 python3 -m lab.cli fault inject bad_credentials
docker compose exec app-server-1 python3 -m lab.cli backup run   # signature mismatch
# ... triage (AUTH_S3 P2) + case ...
docker compose exec app-server-1 python3 -m lab.cli fault clear bad_credentials

# 6. wrong_repo_password
docker compose exec app-server-1 python3 -m lab.cli fault inject wrong_repo_password
docker compose exec app-server-1 python3 -m lab.cli backup run   # wrong password or no key found
# ... triage (AUTH_REPO_PASSWORD P2) + case ...
docker compose exec app-server-1 python3 -m lab.cli fault clear wrong_repo_password

# 7. service_down
docker compose exec app-server-1 python3 -m lab.cli fault inject service_down
docker compose stop minio
docker compose exec app-server-1 python3 -m lab.cli backup run   # no such host
# ... triage (SERVICE_DOWN P1) + case ...
docker compose up -d minio
docker compose exec app-server-1 python3 -m lab.cli fault clear service_down

# after every fault: prove recovery
docker compose exec app-server-1 python3 -m lab.cli backup run   # {"ok": true, ...}
```

Cases land in `cases/CASE-*.md`. Reference write-ups: `docs/incidents/`.

## 13. Detector tuning (justify the threshold)

```bash
docker compose exec app-server-1 python3 -m lab.cli detector tune
# precision 1.0, recall 1.0 over burst + 3 false-positive scenarios
```

## 14. Demo script + Makefile shortcuts

```bash
make demo       # runs sections 8–12 end to end (~5 min, CLI)
make dashboard  # FastAPI + React console at http://localhost:8090 (see below)
make test       # 25 unit tests (lab + API)
make ps         # container status
make logs       # follow all logs
make down       # stop everything (volumes keep your data)
```

### Demo console — FastAPI backend + React frontend (:8090)

Prefer clicking over typing? `make dashboard`, open
http://localhost:8090 in a Windows browser. Full operations console:

- **Health** — 9 services with per-service status, latency, and Docker state
- **Give a file** — pick any file, it lands in `/data/victim` with a SHA-256 fingerprint
- **Protect** — backup + manifest proof your file is inside the new snapshot (refuses honestly if backups are paused)
- **Vault proof** — status + try-delete refused live (immutability)
- **Attack** — guarded simulation with pre-checks (~25 s); detection via alerts counter, not the decaying gauge
- **Restore + verify** — 100% hash check incl. your file, RPO/RTO shown
- **Fault injection** — all 7 faults + clear-all (dns/service host steps handled automatically)
- **Triage + Timeline + Diagnostics** — rule/severity/fix table, chronological event log, service restart (allowlisted, confirm-gated)

API docs (Swagger): http://localhost:8090/docs

**Fresh clone?** The built frontend (`dashboard/frontend/dist/`) is
git-ignored, so build it once before `make dashboard`:

```bash
cd dashboard/frontend && npm ci && npm run build && cd ../..
```

For frontend development with hot reload instead:

```bash
cd dashboard/frontend && npm ci && npm run dev   # :3001, proxies /api → :8090
```

Legacy stdlib console still available: `make dashboard-legacy`.
Requires Node 18+ in WSL (no sudo needed — a `~/node` tarball works).

From Windows PowerShell (thin wrapper): `.\lab.ps1 up`,
`.\lab.ps1 test`, etc.

## 15. Troubleshooting

| Symptom | Fix |
|---|---|
| `docker` not found in Ubuntu | Wait 1–2 min after boot/`wsl --shutdown`; check Docker Desktop → WSL Integration → Ubuntu-24.04 |
| Build fails: `error getting credentials` | `DOCKER_CONFIG=/tmp/dockercfg docker compose build` (see §5) |
| WSL connection drops mid-command (`0x8007274c`) | Just retry; avoid very long single commands; never spam `wsl --shutdown` (kills Docker's distro too) |
| `connection refused` on :9000/:3000/:9090 | `docker compose ps` — start missing service with `docker compose up -d <name>` |
| `vault try-delete` says vault empty | Wait 60 s for vault-sync, retry |
| Backup `deferred` (score elevated) | Normal right after seeding/attack; wait 15 s, retry |
| Backup `skipped` (paused) | An alert fired — intended. `backup resume` after you verify + restore |
| app-server-2 `repository is already locked` | Stale lock from unclean stop: run restic unlock inside it (see `docs/incidents/`, §4 pattern) |
| Detector never alerts | Check `grep alert_raised /var/log/lab/detector.jsonl`; ensure a clean backup ran after the last seed (baselines must be plaintext) |
| Port already in use | `netstat -ano` on Windows, free 9000/9001/9090/3000/8001/8002 |

## 16. Clean slate (start a phase over)

```bash
docker compose down -v   # WARNING: deletes all volumes (data, snapshots, state)
docker compose --env-file .env up -d
```

Without `-v`, `down`/`up` keeps your snapshots and state — safe to
restart containers any time.
