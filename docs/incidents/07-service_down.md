# 07-service_down: object storage container stopped

## Summary
Backup on app-server-1 failed after the MinIO/RustFS container was
stopped. Docker also drops the stopped container's DNS entry, so the
first observable is a lookup failure; `docker compose ps` confirms the
service is down. Triage: SERVICE_DOWN, P1, storage oncall.

## Timeline (UTC, 2026-10-10)
- `lab fault inject service_down` → hint (host action, like spec's table)
- `docker compose stop minio`
- `lab backup run` → exit 1 after ~24s (resolver + client timeouts)
- `lab triage analyze` → SERVICE_DOWN / service / P1
- `lab case create` → CASE-20261010-007
- `docker compose up -d minio` + `lab fault clear service_down`; backup healthy (301 files)

## Symptoms and exact log lines
```
Fatal: unable to open config file: Stat: Get "http://minio:9000/backup-primary/?location=": dial tcp: lookup minio on 127.0.0.11:53: no such host
```

## Diagnosis steps
1. `docker compose ps minio` → Exited: service down, not a client bug.
2. `curl -f http://minio:9000/minio/health/live` → fails (no listener).
3. `docker compose logs minio | tail` → clean stop, no crash loop; distinguish from OOM/crash via exit code.

## Root cause
Object storage service stopped. (Lab note: a stopped container loses its
Docker DNS entry, so the symptom reads as `no such host`; the SERVICE_DOWN
rule owns that pattern while DNS_FAILURE owns `server misbehaving`-style
live-resolver failures. Verified against both real outputs.)

## Resolution
Restarted minio (healthy), cleared fault, backup ok.

## Prevention
- Restart policy + host monitoring on the storage service.
- P1 page on `SnapshotTooOld` / `RansomwareAlert` Prometheus rules.

## Customer-facing update
Backups failed because the storage service was down. We restarted it,
checked its health, and confirmed backups are completing again. Backup
history was preserved throughout.
