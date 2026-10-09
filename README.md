# Backup Resilience Lab

A hands-on learning project for backup operations, data integrity, recovery testing, monitoring, and technical troubleshooting.

## Project goals

- Create repeatable backups of controlled test data.
- Verify backup integrity using cryptographic hashes.
- Test restoration from a known-good backup.
- Monitor service health and backup status.
- Simulate controlled failures and document troubleshooting steps.
- Measure recovery point objective (RPO) and recovery time objective (RTO).

## Planned technology stack

- Ubuntu 24.04 on WSL 2
- Docker Desktop and Docker Compose
- Python
- Restic
- MinIO (S3-compatible object storage)
- Prometheus and Grafana
- Git

## Safety

All failure and encryption simulations will be confined to disposable lab data and isolated containers. No real personal files will be used as test targets.

## Status

Environment setup complete. Implementation and testing are in progress.
