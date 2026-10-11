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

## Demo console (simple frontend, :8080)

```bash
make dashboard   # open http://localhost:8080 in a Windows browser
```

One page that walks the whole data flow with buttons + live status
(detector score, paused flag, clean/suspect counts, last RTO):

1. **Give a file** — uploads your file into `/data/victim` on app-server-1
2. **Backup now** — restic snapshot + manifest (your file is in it)
3. **Vault proof** — status + forced `try-delete` (refused = immutable)
4. **Ransomware attack** — encrypts everything, watch the score cross the
   threshold and backups pause
5. **Restore + verify** — newest clean snapshot, hash-checked, RPO/RTO shown
6. **Fault injection** — all 7 faults, one click each
7. **Triage** — classifies recent failures into rule/severity/fix

Stdlib-only backend (`dashboard/app.py`, no new dependencies); it drives
the lab through `docker compose exec` + host triage. Grafana (:3000)
remains the metrics-only view.
