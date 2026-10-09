# Backup Resilience Lab: End-to-End Implementation Spec (Windows + WSL2)

Hand this document to your coding agent as the single source of truth. Version 1.0, 9 October 2026. Target: Cohesity Technical Support Engineer interview (15 or 16 October 2026).

## 0. How to use this document

1. Read Sections 1 to 3 yourself (goal, Windows setup, architecture).
2. Give the whole document to your agent and tell it to execute Section 14 (phases) in order, obeying Section 15 (agent rules).
3. After each phase, run the acceptance checks yourself. Do not move on if they fail.

## 1. Goal and scope

Build a miniature version of what Cohesity sells (backup, immutable copies, ransomware detection, fast recovery) plus a support-engineer layer (log triage and structured case creation). Everything runs locally on a Windows laptop.

**Five capabilities the finished project must demonstrate:**

1. Scheduled, versioned, deduplicated backups of two "application servers" to S3-compatible object storage.
2. An immutable "vault" copy that cannot be deleted during its retention period (the idea behind Cohesity FortKnox, at lab scale).
3. Detection of a simulated ransomware attack from file entropy and file-change rate, with measured detection time.
4. Recovery from the last clean snapshot with checksum verification and measured recovery time (RTO) and data-loss window (RPO).
5. A triage CLI that reads failure logs, classifies the fault, suggests the fix from a runbook, and writes a support case with severity and routing.

**Non-goals:** a real Cohesity cluster, a web UI beyond Grafana, Kubernetes, cloud accounts, anything that touches real user files.

## 2. Windows setup (do this yourself before the agent starts)

**Why WSL2 + Docker:** the project is Linux-centric (inotify, iptables, cron, restic). The interviewers ask Linux and networking questions, so you want real Linux commands, not Windows equivalents. WSL2 gives a real Linux kernel; Docker Desktop gives containers on top.

**Hardware:** 8 GB RAM minimum (16 GB comfortable), 20 GB free disk, virtualization enabled in BIOS/UEFI.

**Steps (PowerShell as Administrator):**

```powershell
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
# reboot if asked, then create your Linux username/password
```

Then install, as normal Windows apps: Docker Desktop (Settings, General: "Use the WSL 2 based engine"; Settings, Resources, WSL Integration: enable Ubuntu-24.04), Git for Windows, and VS Code with the "WSL" extension.

Optional resource cap, saved as `C:\Users\<you>\.wslconfig`, then run `wsl --shutdown`:

```ini
[wsl2]
memory=6GB
processors=4
swap=2GB
```

**Verify (inside Ubuntu terminal):** `docker version`, `docker compose version`, `python3 --version` (3.11 or newer), `git --version`.

### Windows pitfalls the agent must respect

| Pitfall | Rule |
| --- | --- |
| Slow and broken file watching on `/mnt/c` | Keep the repo in the Linux filesystem, for example `~/projects/backup-resilience-lab`. Never bind-mount a `/mnt/c` path into a container. |
| CRLF line endings break shell scripts | Add `.gitattributes` with `* text=auto eol=lf` and `*.sh text eol=lf`. Create files from inside WSL. |
| inotify not firing on bind mounts from Windows | The watched `/data` directory must be a Docker **named volume**, not a Windows path. |
| Windows Defender may flag the attack simulator | Keep the simulator inside WSL/containers only, never copy it to a Windows folder. If Defender still complains, exclude the WSL project folder and tell no one to run it on real data. |
| Port conflicts | Lab uses 9000, 9001 (MinIO), 9090 (Prometheus), 3000 (Grafana). Check with `netstat -ano` on Windows if a port is taken. |
| PowerShell vs bash | All project commands are bash/Makefile run inside WSL. A thin `lab.ps1` wrapper lets you call them from PowerShell (Section 12). |
| iptables may not work in a container | Containers need `cap_add: [NET_ADMIN]`. If iptables fails, use the documented fallback in Section 11. |

## 3. Architecture

### 3.1 Layers

```
Windows 11 host
  VS Code (WSL extension), PowerShell wrapper lab.ps1
  WSL2 Ubuntu 24.04   <- repo and all Docker volumes live here
    Docker Desktop (WSL2 backend), network: lab-net

      +----------------+   +----------------+
      | app-server-1   |   | app-server-2   |   non-root user: labuser
      | /data (volume) |   | /data (volume) |   agent: backup, detector,
      | lab-agent      |   | lab-agent      |   exporter (:8000)
      +-------+--------+   +--------+-------+
              | restic over S3 (:9000)
              v
      +---------------------------------------+
      | MinIO                                 |
      |  bucket backup-primary (versioned)    |
      |  bucket backup-vault   (object lock)  |
      +--------------------+------------------+
                           ^ mc mirror, one way, every N minutes
                           | (run by the vault-sync sidecar)

      Prometheus (:9090) scrapes app-server-1:8000, app-server-2:8000
      Grafana (:3000) reads Prometheus (provisioned dashboard)
      Triage CLI reads /var/log/lab/*.jsonl and writes cases/
```

### 3.2 Data flows

- **Backup path:** lab-agent runs `restic backup /data` on a schedule, writes a SHA-256 manifest of every file, uploads the manifest to `backup-primary/manifests/`, and records the snapshot in local SQLite as `clean`.
- **Vault path:** vault-sync mirrors `backup-primary` to `backup-vault`. The vault bucket has a default retention, so mirrored objects cannot be deleted or overwritten until expiry.
- **Detection path:** the detector watches `/data` with inotify, computes features over a sliding window, scores them, and on threshold crossing raises an alert.
- **Response path:** alert triggers (1) pause scheduled backups, (2) mark every snapshot taken after the estimated attack start as `suspect` in SQLite, (3) write an alert log line and bump metrics.
- **Recovery path:** `lab restore --latest-clean` picks the newest `clean` snapshot, restores into `/restore`, compares every file hash with the manifest, and reports RTO and RPO.
- **Support path:** failures anywhere write structured JSON logs. `lab triage analyze` classifies them using YAML rules and creates a case file.

### 3.3 Technology choices and why

| Choice | Reason |
| --- | --- |
| restic | Versioned, deduplicated, encrypted snapshots; speaks S3; single binary. Maps to Cohesity DataProtect ideas. |
| MinIO | S3-compatible, supports versioning and object lock, runs in one container. |
| Python 3.11 | Detector, CLI, exporter. Libraries: `watchdog`, `typer`, `prometheus_client`, `pyyaml`, `pytest`, `cryptography` (simulator only). |
| SQLite | Local state (snapshot status, baselines, cases index) with zero setup. |
| Prometheus + Grafana | Standard monitoring stack; interviewers recognise it. |
| Docker Compose | One command brings up the whole lab. |

### 3.4 Design decisions to explain in the interview

- **Why a separate vault bucket instead of object lock on the primary:** restic writes and deletes lock files and prunes old data, which fights with retention rules. Keeping the working repo normal and mirroring to a locked bucket is simpler and mirrors the "air-gapped copy" idea.
- **Why GOVERNANCE retention of 1 day:** COMPLIANCE mode cannot be undone even by the admin, which would trap lab data. GOVERNANCE shows the same behaviour (delete is refused) while staying recoverable by an admin with a bypass flag.
- **Why SQLite for snapshot status instead of restic tags:** retagging rewrites snapshot files; a separate state store keeps the repository itself unchanged and auditable.
- **Why entropy plus change-rate, not entropy alone:** compressed formats (zip, jpg) already have high entropy, so entropy alone causes false positives. Comparing each file against its own baseline and requiring a burst of changes removes most of them.

## 4. Repository layout

```
backup-resilience-lab/
  README.md
  Makefile
  lab.ps1                      # Windows wrapper
  .gitattributes
  .env.example
  docker-compose.yml
  config/
    lab.yaml                   # thresholds, paths, schedules
    triage_rules.yaml          # failure classification rules
  docker/
    agent/Dockerfile           # ubuntu base + restic + python + iptables
    agent/entrypoint.sh
  monitoring/
    prometheus.yml
    grafana/provisioning/{datasources,dashboards}/
    grafana/dashboards/lab.json
  src/lab/
    cli.py                     # typer entry point: `lab ...`
    config.py  logging_setup.py  state.py
    backup.py  manifest.py  vault.py
    detector.py  features.py  response.py
    simulator.py               # guarded attack simulator
    restore.py  verify.py
    exporter.py                # prometheus metrics
    faults.py                  # fault injection / clearing
    triage.py  cases.py
  tests/
    test_features.py test_detector.py test_manifest.py test_triage.py test_faults_parse.py
  docs/
    ARCHITECTURE.md  RUNBOOK.md  RESULTS.md  INTERVIEW_NOTES.md
    incidents/               # one write-up per fault scenario
  cases/                     # generated support cases (git-ignored except samples)
  sample-data/               # generator for dummy files
```

## 5. Infrastructure (docker-compose.yml)

Services and key settings:

| Service | Image / build | Notes |
| --- | --- | --- |
| minio | `minio/minio` | Ports 9000, 9001; volume `minio-data`; credentials from `.env`; healthcheck on `/minio/health/live`. |
| minio-init | `minio/mc` | One-shot: creates `backup-primary` (versioning on) and `backup-vault` (created with object lock, then `mc retention set --default GOVERNANCE 1d`). |
| vault-sync | `minio/mc` | Loop: `mc mirror --overwrite backup-primary backup-vault` every `vault_sync_seconds`. Never deletes from vault. |
| app-server-1, app-server-2 | build `docker/agent` | User `labuser` (non-root); `cap_add: [NET_ADMIN]`; named volume `data1`/`data2` at `/data`; tmpfs `/cache` size 64m (restic cache, used by the disk-full fault); volume `logs` at `/var/log/lab`; exposes 8000. |
| prometheus | `prom/prometheus` | Scrapes both agents every 5s. |
| grafana | `grafana/grafana` | Provisioned datasource and dashboard, anonymous viewer allowed for the demo. |

**Agent image:** Ubuntu 24.04, `restic`, `python3`, `pip`, `iptables`, `iproute2`, `dnsutils`, `procps`, `net-tools`, `curl`, `cron` or a Python scheduler loop. Install the `lab` package with `pip install -e .`. Entrypoint starts: the exporter, the detector, and the backup scheduler as separate processes (use `supervisord` or a small Python launcher).

**Secrets:** `.env` holds `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `RESTIC_PASSWORD`. Provide `.env.example`; never commit `.env`.

## 6. Backup subsystem

**Repository:** `s3:http://minio:9000/backup-primary/<hostname>` (one repo path per server).

**Run cycle (`backup.py`), every `backup_interval_seconds` (default 120 for the demo):**

1. If backups are paused (flag in SQLite), log and skip.
2. Build manifest: walk `/data`, SHA-256 each file, store `{path, size, sha256, mtime}`.
3. `restic backup /data --tag lab --json`; capture snapshot ID from the JSON summary.
4. Upload manifest to `s3://backup-primary/manifests/<hostname>/<snapshot_id>.json`.
5. Insert row in SQLite `snapshots(id, host, taken_at, status='clean', files, bytes)`.
6. Emit metrics and one JSON log line with duration, files, bytes.
7. Every Nth run, execute `restic check` and log the result. Do **not** run `restic forget --prune` against the primary during the demo.

**Error handling:** every restic failure is wrapped, the stderr is kept verbatim in the log line field `raw`, and the exit code is recorded. Never swallow errors; the triage tool depends on them.

**Vault (`vault.py`):** provide `lab vault status` (object count, retention setting) and `lab vault try-delete` which attempts to delete a vault object and must fail with an access-denied style error; this is a demo step.

## 7. Ransomware simulation (safe by design)

**Purpose:** generate realistic file behaviour for the detector. It is a lab-only simulation on dummy data.

**Mandatory safety guards in `simulator.py` (refuse to run if any fail):**

1. Target directory must equal the configured lab path (default `/data/victim`).
2. A sentinel file `/data/victim/.LAB_SAFE_TO_ENCRYPT` must exist.
3. Running inside a container (check `/.dockerenv`).
4. No network calls, no persistence, no spreading, no process injection. Keys are random per run and written to `/var/log/lab/sim_key_<run_id>.key` so everything is reversible.

**Behaviour:** after a configurable delay, iterate files in the target, read, encrypt with an AES-based library call (Fernet), overwrite, rename with `.locked`, at a configurable rate (default 15 files/second), and drop `README_LAB_NOTE.txt`. Log `attack_start` and `attack_end` timestamps to the JSON log so the detection latency can be measured against ground truth.

**Sample data generator (`sample-data/`):** create about 300 files per server in `/data/victim`: 70% plain text, CSV and JSON, 20% DOCX-like (zip), 10% JPG-like binary. The mix is deliberate: it exposes the false-positive problem with compressed files.

## 8. Detection subsystem

**Inputs:** inotify events from `watchdog` on `/data` (create, modify, move, delete).

**Features over a sliding window (default 10 seconds), in `features.py`:**

| Feature | Definition |
| --- | --- |
| `mod_rate` | Distinct files modified in the window |
| `entropy_jump` | For files modified in the window, mean of (Shannon entropy of first 64 KB now minus stored baseline entropy) |
| `high_entropy_ratio` | Share of modified files whose entropy exceeds 7.5 bits per byte **and** whose baseline was below 7.0 |
| `ext_change` | Count of renames that change the extension to a new, previously unseen one |
| `note_files` | New files with identical content across directories (ransom-note pattern) |

**Baseline:** on startup, scan `/data` and store per-file entropy in SQLite. Update baselines only after a backup is marked `clean`, otherwise the detector would learn encrypted content as normal.

**Score and decision (`detector.py`):**

```
score = 0.35*norm(mod_rate) + 0.35*high_entropy_ratio
      + 0.20*norm(ext_change) + 0.10*min(note_files,1)
alert if score >= threshold (default 0.6) for 2 consecutive windows
```

All weights and thresholds live in `config/lab.yaml`. Provide a `lab detector tune` command that replays recorded event logs and prints precision/recall so thresholds can be justified with numbers.

**False-positive tests (must pass):** (a) normal edits to text files at low rate, (b) a legitimate bulk copy of JPG-like files (high entropy but baseline is also high), (c) one large zip being rewritten.

**Response (`response.py`) on alert:**

1. Log `alert_raised` with score, features, and `detected_at`.
2. Set `backups_paused = true`.
3. Estimate `attack_start` as the earliest event in the offending windows; mark snapshots with `taken_at >= attack_start - safety_margin` (default 5 seconds) as `suspect`.
4. Increment `lab_alerts_total`; set gauge `lab_detector_score`.
5. Print recommended next command: `lab restore --latest-clean`.

## 9. Recovery and verification

`lab restore --latest-clean --host app-server-1`:

1. Select newest SQLite snapshot with status `clean` for that host.
2. `restic restore <id> --target /restore/<run_id>`.
3. Download its manifest; verify every file by SHA-256; report missing, corrupted, or extra files.
4. Compute and print:
   - **Detection latency** = `detected_at` minus `attack_start` (ground truth from simulator log)
   - **RPO** = `attack_start` minus `taken_at` of the restored snapshot
   - **RTO** = `verified_at` minus `restore_started_at`
   - **Recovery success** = percentage of manifest files that verified
5. Append the run to `docs/RESULTS.md` (table row) and export metrics.

**Acceptance:** 100% of files from the clean snapshot verify; a deliberately corrupted restore (flip one byte) is caught and reported.

## 10. Monitoring and observability

**Exporter (`exporter.py`)** on port 8000 per agent, using `prometheus_client`:

| Metric | Type | Meaning |
| --- | --- | --- |
| `lab_backup_last_success_timestamp` | gauge | Unix time of last good backup |
| `lab_backup_duration_seconds` | histogram | Backup runtime |
| `lab_backup_failures_total` | counter (label `category`) | Failures by triage category |
| `lab_snapshots_total` | gauge (label `status`) | clean vs suspect |
| `lab_repo_size_bytes` | gauge | Repository size |
| `lab_detector_score` | gauge | Current score |
| `lab_alerts_total` | counter | Ransomware alerts |
| `lab_backups_paused` | gauge | 0 or 1 |
| `lab_last_restore_rto_seconds` | gauge | Last RTO |

**Grafana dashboard (provisioned JSON):** panels for snapshot age (now minus last success), backup success/failure over time, detector score with threshold line, clean vs suspect snapshots, repo size, last RTO. Add a Prometheus alert rule file `snapshot_age > 10 minutes` (visible in the Prometheus UI is enough; Alertmanager is optional).

**Logging standard:** one JSON object per line in `/var/log/lab/<component>.jsonl` with fields `ts` (UTC ISO 8601), `level`, `host`, `component`, `event`, `message`, `exit_code` (optional), `raw` (optional). Use this everywhere; the triage tool depends on it.

## 11. Fault injection (the troubleshooting layer)

`faults.py` exposes `lab fault inject <name>` and `lab fault clear <name>`, executing inside the target container with `docker compose exec`.

| # | Name | Injection | Expected symptom | Category | Likely fix |
| --- | --- | --- | --- | --- | --- |
| 1 | `disk_full` | `fallocate -l 60M /cache/fill` on the 64 MB tmpfs | `no space left on device` | storage | Free space, clear cache, resize volume |
| 2 | `dns_failure` | Overwrite `/etc/resolv.conf` with an unreachable nameserver and use hostname `minio` through a non-Docker resolver path | `lookup minio ... timeout` or `no such host` | dns | Restore resolver, check `dig`, `/etc/resolv.conf` |
| 3 | `port_blocked` | `iptables -A OUTPUT -p tcp --dport 9000 -j DROP` | `dial tcp ... i/o timeout` | network | Remove rule, test with `nc -vz minio 9000` |
| 4 | `permission_denied` | `chmod 000 /data/victim/finance` (agent runs as non-root) | `permission denied` warnings, incomplete snapshot | permissions | Fix mode/ownership, rerun backup |
| 5 | `bad_credentials` | Override S3 secret key env var, restart agent | `Access Denied` or `SignatureDoesNotMatch` | auth | Rotate or correct credentials |
| 6 | `wrong_repo_password` | Change `RESTIC_PASSWORD`, restart agent | `wrong password or no key found` | auth | Restore correct secret from vault |
| 7 | `service_down` | `docker compose stop minio` | `connection refused` | service | Start service, check health endpoint |

**Fallbacks:** if `iptables` fails in the container, use `docker network disconnect lab-net app-server-1` for the port-blocked scenario and document the substitution. Each `clear` must fully undo its injection; add a `lab fault clear --all` command and test it.

**Deliverable per fault:** `docs/incidents/NN-<name>.md` with sections: Summary, Timeline, Symptoms and exact log lines, Diagnosis steps (real commands such as `df -h`, `ss -tnp`, `dig`, `ls -l`, `journalctl`-style log review), Root cause, Resolution, Prevention, Customer-facing update (three sentences, plain language).

## 12. Triage CLI and support cases

**Commands:**

```
lab triage analyze <logfile> [--since 1h]   # classify failures, print table
lab case create <logfile>                   # generate a support case
lab case list | lab case show <case-id>
```

**Rules file (`config/triage_rules.yaml`), each rule:**

```yaml
- id: STORAGE_DISK_FULL
  category: storage
  severity: P2
  match: ["no space left on device", "disk quota exceeded"]
  cause: "Local cache or volume is out of space"
  checks: ["df -h", "du -sh /cache /data"]
  fix: "Free space or enlarge the volume, then rerun the backup"
  route: "Support L1 - self-resolve with runbook"
```

Rules must exist for all seven fault scenarios plus a catch-all `UNKNOWN` (severity P3, route to L2 with raw logs attached). Matching is case-insensitive regex over `message` and `raw`; the most specific rule (most matched patterns) wins; ties go to the higher severity.

**Severity guideline:** P1 = no successful backup for more than 3 intervals or ransomware alert active; P2 = repeated failures or partial backups; P3 = single transient failure; P4 = informational.

**Case output (`cases/CASE-YYYYMMDD-NNN.md` and `.json`):** title, severity, category, affected host, first and last occurrence, occurrence count, environment (OS, restic version, container image), symptom (verbatim log lines), checks performed, probable cause, recommended fix, escalation route, status, customer update text. Also index cases in SQLite.

**Windows wrapper `lab.ps1`:**

```powershell
param([Parameter(ValueFromRemainingArguments=$true)]$Args)
wsl -d Ubuntu-24.04 -- bash -lc "cd ~/projects/backup-resilience-lab && make $Args"
```

The Makefile targets map one to one: `make up`, `make down`, `make seed`, `make attack`, `make restore`, `make fault NAME=disk_full`, `make clear`, `make test`, `make demo`.

## 13. Testing strategy

| Level | What | Tool |
| --- | --- | --- |
| Unit | Entropy function (known inputs), feature windows, manifest hashing, triage rule matching, config parsing | pytest |
| Integration | Backup then restore round trip; vault delete refusal; each fault inject/clear pair produces the expected triage category | pytest + docker compose |
| Scenario | Full attack, detect, restore run, repeated 5 times; record median detection latency and RTO | `make demo` script |
| Negative | The three false-positive scenarios in Section 8 produce no alert | pytest |

Target: all tests pass with `make test`; CI is optional (a simple GitHub Actions workflow running unit tests is a good bonus).

## 14. Implementation phases and acceptance criteria

| Phase | Work | Acceptance check (human verifies) |
| --- | --- | --- |
| 1. Foundation (Day 1) | Repo, `.gitattributes`, Makefile, compose with MinIO and buckets, agent image, config and logging module | `make up` is healthy; MinIO console reachable at localhost:9001; both buckets exist; vault has retention |
| 2. Backup (Day 1 to 2) | `backup.py`, manifest, SQLite state, scheduler, vault-sync | New snapshots appear every interval; manifests uploaded; objects appear in vault; `lab vault try-delete` is refused |
| 3. Restore (Day 2) | `restore.py`, `verify.py` | Restore verifies 100%; corrupted file is detected |
| 4. Attack and detect (Day 3) | Sample data, simulator with guards, features, detector, response | Alert within a few seconds of attack start; backups pause; suspect snapshots marked; false-positive tests pass |
| 5. Full recovery run (Day 3) | End-to-end `make demo`, metrics into RESULTS.md | Five runs recorded with detection latency, RPO, RTO |
| 6. Monitoring (Day 4) | Exporter, Prometheus, Grafana dashboard | Dashboard shows all panels live during a demo |
| 7. Faults and triage (Day 4) | `faults.py`, rules, case generator, seven incident write-ups | Each fault yields the right category and a case file; clear undoes it |
| 8. Polish (Day 5) | README with architecture diagram, demo script, INTERVIEW\_NOTES.md, tests green | A new person can run the demo from the README alone |

**Cut order if time runs short:** Grafana polish first, then `detector tune`, then faults 6 and 7, then CI. Never cut backup, vault, detector, restore, or triage.

## 15. Rules for the coding agent

1. Follow the repo layout and names in this document. If a change is needed, update `docs/ARCHITECTURE.md` and say why.
2. Work phase by phase. Stop at the end of each phase, print how to verify it, and wait for approval.
3. Create and edit files from inside WSL only. Never place project files or bind mounts under `/mnt/c`.
4. Pin versions in `requirements.txt` and image tags in compose (no `latest`).
5. Never hard-code secrets. Use `.env`.
6. The simulator must keep every guard in Section 7. Never point it at any path outside the lab volume, and never add spreading, persistence, or network behaviour.
7. **Never fabricate results.** Every number in `docs/RESULTS.md` must come from an actual run, with date and commit hash. If something does not work, write down what failed instead of hiding it.
8. Verify the object lock and restic behaviour with a real test before relying on it (create object, attempt delete, record outcome). If behaviour differs from this spec, report it and propose the smallest change.
9. Write tests alongside code. Do not mark a phase complete with failing tests.
10. Keep commits small with clear messages (`feat:`, `fix:`, `docs:`, `test:`).
11. Ask the human only when blocked; otherwise choose the simplest option that satisfies the spec and note the decision.

## 16. Demo script (5 minutes, for the interview or screen share)

1. `make up` and open Grafana: show healthy backups and snapshot age.
2. Show the vault: `lab vault try-delete` fails. Say: immutability.
3. `make attack`: watch the detector score climb on the dashboard; alert fires; backups pause.
4. `make restore`: show verification at 100% and the measured RPO and RTO.
5. `make fault NAME=dns_failure`: backup fails; run `lab triage analyze`; show the generated case with severity and routing; run the diagnosis commands manually (`dig`, `cat /etc/resolv.conf`); `make clear`.

## 17. Interview notes to prepare (fill in with your real numbers)

- **One-sentence pitch:** "I built a small backup and recovery platform with an immutable vault, a ransomware behaviour detector, and a support triage tool that turns failure logs into structured cases."
- **Be ready to explain:** how restic deduplicates and encrypts; what an S3 object lock does; why entropy alone gives false positives; what RPO and RTO mean and what yours were; how DNS, TCP and DHCP failures look different in logs; what `ss -tnp`, `df -h`, `dig`, `tcpdump` show; why Docker named volumes differ from bind mounts.
- **Be honest:** say it is a lab-scale model of Cohesity ideas, not their product. Show what you measured, and mention what you would improve (multi-site replication, real ML model, role-based access, alert routing).
- **Resume bullets:** use the four bullets from the earlier research doc, replacing X and N with values from `docs/RESULTS.md`.

## 18. Definition of done

- `make up`, `make demo`, and `make test` work on a clean clone inside WSL2.
- RESULTS.md contains five recorded recovery runs with real numbers.
- Seven incident write-ups exist and match the rules in `triage_rules.yaml`.
- README includes the architecture diagram, setup for Windows, and the demo script.
- You can explain every component without reading notes.
