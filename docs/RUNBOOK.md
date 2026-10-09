# Runbook (extract)

## Backup failing?
1. `lab triage analyze /var/log/lab/backup.jsonl | tail`
2. `df -h; du -sh /cache /data` (disk_full)
3. `cat /etc/resolv.conf; dig minio` (dns)
4. `iptables -L OUTPUT -n -v; nc -vz minio 9000` (network)
5. `ls -l /data/victim` (permissions)
6. `curl -f http://minio:9000/minio/health/live; docker compose ps minio` (service)

## Ransomware alert?
1. `grep alert_raised /var/log/lab/*.jsonl | tail`
2. `lab restore --latest-clean --host app-server-1`
3. Verify 100%, record RTO/RPO in RESULTS.md.

## Vault check
`lab vault status` + `lab vault try-delete` (must be refused).
