# 02-dns_failure: container lost name resolution for MinIO

## Summary
Backup on app-server-1 failed: the container could not resolve `minio`
after being disconnected from `lab-net` (cable-pull equivalent). Triage:
DNS_FAILURE, P2, network runbook.

## Timeline (UTC, 2026-10-10)
- `lab fault inject dns_failure` → reports host mechanism (see Root cause)
- `docker network disconnect backup-resilience-lab_lab-net <app-server-1>`
- `lab backup run` → exit 1 in ~5s, lookup failure
- `lab triage analyze` → DNS_FAILURE / dns / P2
- `lab case create` → CASE-20261010-002
- `docker network connect ...` + `lab fault clear dns_failure`; backup healthy

## Symptoms and exact log lines
```
Fatal: unable to open config file: Stat: Get "http://minio:9000/backup-primary/?location=": dial tcp: lookup minio on 127.0.0.11:53: server misbehaving
```

## Diagnosis steps
1. `cat /etc/resolv.conf` → Docker embedded DNS 127.0.0.11 (unchanged).
2. `getent hosts minio` → fails; `docker network inspect lab-net` → container missing.
3. `dig minio @127.0.0.11` → SERVFAIL/misbehaving: resolver reachable, name unknown off-network.

## Root cause
Container detached from lab-net. (Lab note: in-container DNS sabotage is
not possible on Docker Desktop — vsock DNS bypasses netfilter and
resolv.conf/nsswitch.conf are read-only mounts — so the documented
substitution is host-side disconnect, which yields a genuine lookup
failure. See ARCHITECTURE.md.)

## Resolution
Reconnected container to lab-net; cleared fault; backup ok (301 files).

## Prevention
- Alert on repeated DNS-category failures per host.
- Netplan/Docker healthcheck on `getent hosts minio`.

## Customer-facing update
Backups failed because the worker temporarily could not reach the storage
address book. We restored its network connection and confirmed the next
backup completed. Your data was never at risk.
