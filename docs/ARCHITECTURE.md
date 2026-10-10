# Architecture (spec Section 3)

Source of truth for intent: `docs/Backup Resilience Lab End-to-End Implementation Spec (Windows + WSL2) (1).md`.
This file documents what was built and every place reality forced a
deviation (spec rule 15.1/15.8: verify behaviour, report differences,
smallest change).

```
Windows 11 host
  VS Code (WSL extension), PowerShell wrapper lab.ps1
  WSL2 Ubuntu 24.04  <- repo and all Docker volumes live here
    Docker Desktop (WSL2 backend), network: lab-net
      app-server-1, app-server-2 (non-root labuser, /data named volume,
        lab-agent: exporter :8000 + detector + backup loop, config mounted)
        | restic 0.16.4 over S3 (:9000), XDG_CACHE_HOME+TMPDIR=/cache (64M tmpfs)
        v
      storage "minio" (RustFS 1.0.1, S3-compatible, service name kept):
        backup-primary (versioned) + backup-vault (versioned, ObjectLock GOVERNANCE 1d)
        ^ aws-cli `s3 sync` one-way every 60s (vault-sync sidecar, never --delete)
      Prometheus (:9090) <- scrapes agents; Grafana (:3000) reads Prometheus
      Triage CLI reads /var/log/lab/*.jsonl and writes cases/ (host-side)
```

## Data flows
- Backup: manifest walk (SHA-256 + readability probes) → restic backup →
  manifest to `backup-primary/manifests/` → SQLite row (`clean`, or
  `suspect` when partial). Preflight: /cache free-space gate + anomaly
  deferral while detector score elevated. Baselines refresh only from clean
  snapshots; stale baseline paths pruned.
- Vault: sync mirrors primary→vault; version-targeted delete is refused
  with AccessDenied under GOVERNANCE retention (verified live).
- Detection: watchdog inotify → 10s sliding window → score =
  0.35·norm(mod_rate) + 0.35·high_entropy_ratio + 0.20·norm(ext_change) +
  0.10·note_files; alert at ≥0.55 for 2 consecutive windows.
- Response: pause backups (SQLite flag), mark snapshots after
  attack_start−5s as suspect, log alert, bump metrics.
- Recovery: newest `clean` snapshot → `/restore/<run>` → SHA-256 verify vs
  manifest → RTO/RPO/detection-latency; row appended to RESULTS.md.
- Support: JSONL logs → YAML rules (refined from observed real errors) →
  case files + SQLite index.

## Verified deviations / findings (all proven by real runs, Oct 2026)

1. **RustFS + aws-cli instead of MinIO + mc.** MinIO deleted
   `minio/minio` and `minio/mc` from Docker Hub (Sep 2026; pulls 404).
   RustFS 1.0.1 (Apache-2.0, S3, versioning + ObjectLock WORM verified)
   is the drop-in; `amazon/aws-cli` replaces `mc` for init/sync. Service
   name stays `minio`, so app code is unchanged.
2. **Vault bucket must be versioned too.** S3 Object Lock needs
   versioning; without it a plain delete succeeded. minio-init enables
   versioning + lock on both buckets. `vault try-delete` targets the live
   VersionId (plain deletes only hide behind a delete marker on versioned
   buckets); version delete is refused: `AccessDenied ... under GOVERNANCE
   retention`.
3. **Threshold 0.55 (spec: 0.6).** First real attack scored 0.595: the
   `.locked` extension was already known from an earlier run, dropping the
   ext term. `lab detector tune` still reports precision/recall 1.0.
4. **high_entropy_ratio is baseline-relative** (`entropy_jump_min: 1.5`
   bits, OR-ed with absolute 7.5). Measured AES-CTR ciphertext of sub-KB
   files is only ~7.4–7.7 bits (short-sample estimate), so absolute 7.5
   misses small files while their +2.5–3.5-bit jump is unambiguous.
   Already-compressed files (baseline ≥7.0) stay excluded in both branches.
5. **Moved events link to source baselines; identities grouped by
   file.** Two stacked bugs: renames inflated the ratio denominator
   without contributing (fixed: denominator = identities with baselines),
   and the handler reads modified files *after* ransomware renames them
   (stale entropy 0.0; the move carries the real entropy). Both proven
   with targeted repros.
6. **Simulator uses raw AES-256-CTR, not Fernet.** Fernet emits base64
   (~6 bits/byte) — undetectable at any sane threshold and unlike real
   ransomware (raw AES ~8 bits). Per-file random IV prepended; per-run key
   stored in the log dir (reversible). Guards/rate/notes unchanged, plus
   shuffled traversal and per-directory identical notes (realistic, and
   stabilises the window mix).
7. **Exporter is a pull adapter.** exporter/detector/backup are separate
   processes; in-memory prometheus_client values never cross processes.
   On each scrape the exporter rebuilds gauges from SQLite/kv and tails
   JSONL logs (host-filtered) for durations/failures. Metric names/types
   match the spec exactly.
8. **Config is mounted** (`./config:/app/config:ro`); the image previously
   ran on compiled-in defaults. Triage rules likewise live-reload.
9. **Least-privilege sudo for iptables only** (`labuser NOPASSWD:
   iptables`). Non-root agent + NET_ADMIN still can't touch netfilter;
   sudoers drop-in fixes it without root containers. tmpfs needs
   `mode=1777` (runtime tmpfs masks image ownership).
10. **Backup preflight + deferral + partial handling.** /cache free-space
    gate (10 MB) makes disk_full deterministic (restic tolerates 95%
    pressure at lab scale); defer while detector score ≥0.3 so mid-attack
    backups neither record dirty snapshots nor poison baselines;
    restic --json hides causes, so failures are enriched from the
    manifest's own readability probes; partial snapshots → suspect.
11. **Fault mechanisms per environment.** Docker Desktop: resolv.conf and
    nsswitch.conf are read-only mounts and its vsock DNS bypasses
    netfilter → dns_failure uses host-side `network disconnect` (genuine
    `lookup minio ... server misbehaving`); port_blocked works via
    sudo-iptables (`i/o timeout` verified); service_down via
    `compose stop` (Docker drops the name too → `no such host`, owned by
    the SERVICE_DOWN rule with container-state diagnosis). Rules were
    extended only with literally observed texts (incl. RustFS SigV4 prose).
12. **Restore uses latest attack/alert log lines** (first-match gave stale
    RPO across repeated runs).
13. **click==8.1.8 pinned** (typer 0.12.5 breaks on click 8.2+ rich help).
14. **Layout notes.** Legacy `app/`, `configs/`, `grafana/`, `prometheus/`
    stub dirs removed; canonical tree is spec Section 4 (`config/`,
    `monitoring/`, `docker/`, `src/lab/`, `sample-data/`, `cases/`,
    `docs/incidents/`).

## Design decisions (spec 3.4, kept)
- Separate vault bucket (restic lock/prune vs retention).
- GOVERNANCE 1d, not COMPLIANCE (recoverable in lab).
- SQLite sidecar for snapshot status (no snapshot rewriting).
- Entropy + change-rate (zip/jpg already high-entropy).

## Measured (docs/RESULTS.md, 5 runs)
- Detection latency median 9.88 s (range 6.6–10.2 s), RPO 12.6–23.3 s,
  RTO 1.2–2.4 s, recovery success 100% (301/301) every run.
