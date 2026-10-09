# Architecture (spec Section 3)

See spec: `docs/Backup Resilience Lab End-to-End Implementation Spec (Windows + WSL2) (1).md`.

```
Windows 11 host
  VS Code (WSL extension), PowerShell wrapper lab.ps1
  WSL2 Ubuntu 24.04  <- repo and all Docker volumes live here
    Docker Desktop (WSL2 backend), network: lab-net
      app-server-1, app-server-2 (labuser, /data named volume, lab-agent, exporter :8000)
        | restic over S3 (:9000)
        v
      MinIO: backup-primary (versioned) + backup-vault (object lock GOVERNANCE 1d)
        ^ mc mirror one-way every N min (vault-sync sidecar)
      Prometheus (:9090) <- scrapes agents; Grafana (:3000) reads Prometheus
      Triage CLI reads /var/log/lab/*.jsonl and writes cases/
```

## Data flows
- Backup: lab-agent `restic backup /data` on schedule + SHA-256 manifest to `backup-primary/manifests/` + SQLite row `clean`.
- Vault: `mc mirror --overwrite` primary -> vault (locked bucket, delete refused).
- Detection: inotify via watchdog, sliding 10s window, score = 0.35*norm(mod_rate)+0.35*high_entropy_ratio+0.20*norm(ext_change)+0.10*note_files, alert if >=0.6 for 2 windows.
- Response: pause backups, mark snapshots after attack_start-margin as suspect, log alert, bump metrics.
- Recovery: newest `clean` snapshot -> `/restore/<run>` -> SHA-256 verify vs manifest -> RTO/RPO.
- Support: JSONL logs -> YAML rules -> case files.

## Deviations from spec layout
- Spec `config/` implemented as `config/` (repo also has legacy empty `configs/` dir, unused).
- Spec `monitoring/` implemented as `monitoring/` (legacy `prometheus/`, `grafana/` dirs left empty for compat).
- Spec `src/lab/` implemented as `src/lab/` (legacy `app/main.py` kept but unused; agent uses `lab` package).
- `docker-compose.yml` pins: minio RELEASE-2025-04-22, mc RELEASE-2025-04-16, prometheus v3.3.0, grafana 11.5.2, ubuntu 24.04.

## Design decisions (spec 3.4)
- Separate vault bucket (restic lock/prune fights retention on primary).
- GOVERNANCE 1d (not COMPLIANCE, so lab data recoverable with bypass).
- SQLite for snapshot status (retagging rewrites snapshots; sidecar DB keeps repo auditable).
- Entropy + change-rate (zip/jpg already high entropy; baseline comparison + burst requirement kills FPs).
