# 03-port_blocked: egress to object storage dropped

## Summary
Backup on app-server-1 failed with TCP timeout to minio:9000 after an
iptables OUTPUT DROP was added (least-privilege sudo). Triage:
NETWORK_PORT_BLOCKED, P2, network runbook.

## Timeline (UTC, 2026-10-10)
- `lab fault inject port_blocked` → `sudo -n iptables -A OUTPUT -p tcp --dport 9000 -j DROP` (mechanism: iptables; probe confirmed port unreachable)
- `lab backup run` → exit 1, i/o timeout
- `lab triage analyze` → NETWORK_PORT_BLOCKED / network / P2
- `lab case create` → CASE-20261010-003
- `lab fault clear port_blocked` → rule deleted; backup healthy

## Symptoms and exact log lines
```
Fatal: unable to open config file: Stat: Get "http://minio:9000/backup-primary/?location=": dial tcp 172.20.0.2:9000: i/o timeout
```

## Diagnosis steps
1. `sudo iptables -L OUTPUT -n -v` → DROP rule for dport 9000 with packet count rising.
2. `curl -m 4 http://minio:9000/minio/health/live` → timeout; `getent hosts minio` → resolves (DNS fine, TCP blocked).
3. `ss -tnp` → SYN_SENT stuck: classic egress filter, not a dead server.

## Root cause
Host/container firewall dropping outbound TCP/9000. (Lab note: labuser
runs iptables via NOPASSWD sudo restricted to the iptables binary;
non-root agent keeps least privilege. See Dockerfile.)

## Resolution
Deleted the DROP rule; verified with curl; backup ok.

## Prevention
- Audit firewall rules in config management; alert on `lab_backup_failures_total{category="network"}`.
- Pre-backup `nc -vz minio 9000` probe with clear error.

## Customer-facing update
Backups failed because a firewall rule blocked the path to storage. We
removed the blocking rule, verified connectivity, and backups resumed
normally. No data was lost.
