# Backup Resilience Lab

A lab-scale backup & recovery platform with an immutable vault, a
behavioural ransomware detector, and a support triage tool that turns
failure logs into structured cases. 

## Architecture

```
Windows 11 → WSL2 Ubuntu 24.04 → Docker (lab-net)
  app-server-1/2 (lab-agent: scheduled restic backups + detector + :8000 metrics)
  storage "minio" = RustFS (S3): backup-primary (working) → mirror → backup-vault (GOVERNANCE lock 1d)
  Prometheus :9090 → Grafana :3000 dashboard
  lab CLI: backup / restore / attack / detector / vault / fault / triage / case
```

Details + all verified deviations: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Spec: [docs/Backup Resilience Lab End-to-End Implementation Spec (Windows + WSL2) (1).md](docs/Backup%20Resilience%20Lab%20End-to-End%20Implementation%20Spec%20(Windows%20+%20WSL2)%20(1).md).

## Setup (Windows + WSL2)

```powershell
wsl --install -d Ubuntu-24.04   # then Docker Desktop (WSL2 backend, enable Ubuntu integration), Git, VS Code+WSL
git clone <repo> ~/projects/backup-resilience-lab
```

```bash
cd ~/projects/backup-resilience-lab
cp .env.example .env
make build && make up     # MinIO console :9001, Prometheus :9090, Grafana :3000
make test                 # 15 unit tests (entropy, detector incl. FPs, manifest/verify, triage, fault catalog)
```

WSL notes: keep the repo in the Linux fs (`~/projects/...`, never `/mnt/c`);
files are LF (`* text=auto eol=lf`); if `make build` fails with a
credentials error, use `DOCKER_CONFIG=/tmp/dockercfg docker compose build`.

## Demo (5 minutes)

```bash
make demo
```

1. `make up` → Grafana shows healthy backups, snapshot age ~0.
2. `lab vault try-delete` → **refused** (`AccessDenied`, GOVERNANCE retention). Immutability.
3. `make attack` → detector score climbs, alert in ~7–10 s, backups pause, post-attack snapshots marked suspect.
4. `make restore` → 100% SHA-256 verify + RPO/RTO printed (medians: latency 9.9 s, RPO ~19 s, RTO ~2.1 s).
5. `make fault NAME=dns_failure` → backup fails → `lab triage analyze` → P2 case with fix + route → `make clear`.

## Measured results

[docs/RESULTS.md](docs/RESULTS.md) — 5 attack→detect→restore runs, all 100% (301/301 files):

| run | detection latency | RPO | RTO |
|---|---|---|---|
| 1–5 | 9.95 / 6.62 / 7.94 / 10.23 / 9.88 s | 12.6–23.3 s | 1.2–2.4 s |

Plus: [docs/RUNBOOK.md](docs/RUNBOOK.md), 7 write-ups in [docs/incidents/](docs/incidents/)
(one per fault, with real log lines + fixes), 7 generated cases in [cases/](cases/),
[docs/INTERVIEW_NOTES.md](docs/INTERVIEW_NOTES.md).

## CLI map

`lab seed | backup run/loop | vault status/try-delete | attack run |
detector run/tune | restore --latest-clean --host H | fault inject/clear |
triage analyze <log> | case create/list/show | exporter`

## Demo Console & Live Monitored Frontend (:8090)

The lab includes a modern, live-monitored React + FastAPI operations dashboard (`dashboard/frontend/` and `dashboard/api.py`).

### Quick Start:

```bash
# 1. Install Python requirements & build frontend:
pip install -r requirements.txt
make frontend-build    # builds React app into dashboard/frontend/dist

# 2. Start the dashboard backend (serves frontend + API at port 8090):
make dashboard         # or: python3 dashboard/api.py --port 8090
```

Open **`http://localhost:8090`** in any browser.

For frontend development with live hot-reloading:
```bash
cd dashboard/frontend
npm run dev            # runs on http://localhost:3001 (proxies /api to :8090)
```

### Dashboard Workflow & Features:

1. **Live System Health**: Real-time polling every 5s covering RustFS S3, App Servers, Vault, Detector, Prometheus (:9090), and Grafana (:3000). Visual status badges (`HEALTHY`, `DEGRADED`, `OFFLINE`).
2. **Offline Handling**: If the backend is stopped or unreachable, the UI gracefully renders an offline status card with timestamps and copyable WSL commands (`docker compose ps`, `python dashboard/api.py`).
3. **Protect a File**: Drag-and-drop sample upload to `/data/victim` with client + server SHA-256 fingerprinting, backup snapshot generation, and catalog tracking.
4. **Monitoring & Watchdog**: Live entropy score meter vs threshold (0.55), alert status, backup circuit-breaker status, and resume control.
5. **Guarded Attack Simulation**: Controlled ransomware simulation with pre-flight checks (refuses to run unless a clean backup exists). Distinguishes simulation completion from actual detector trigger.
6. **Recovery & Verification**: Restores the latest clean snapshot into `/data/restore`, executes cryptographic SHA-256 manifest verification, and validates sample fingerprints.
7. **System Diagnostics**: Deep multi-check inspection returning Pass/Fail, observed behavior, likely cause, and recommended action.
8. **Activity Timeline**: Chronological event stream tracking real backup, attack, restore, and health events.
9. **Safe Service Recovery**: Allowlisted service restart with confirmation modal (`minio`, `app-server-1`, `app-server-2`, `prometheus`, `grafana`).

Legacy minimal console remains available via: `make dashboard-legacy`.

