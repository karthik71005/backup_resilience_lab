# Interview notes

Pitch: "I built a small backup and recovery platform with an immutable vault, a ransomware behaviour detector, and a support triage tool that turns failure logs into structured cases."

- restic: content-defined chunking, deduplication, AES-256 encryption, S3 backend.
- S3 object lock GOVERNANCE 1d: delete/overwrite refused until expiry (COMPLIANCE stricter, irreversible).
- Entropy alone FPs on zip/jpg (already ~7.5-8 bits/byte); baseline delta + burst rate fixes it.
- RPO = attack_start - snapshot_taken (data-loss window); RTO = verified_at - restore_started (downtime). See RESULTS.md.
- DNS vs TCP vs service-down: `no such host` vs `i/o timeout` vs `connection refused`. Tools: `ss -tnp`, `df -h`, `dig`, `tcpdump`, `iptables -L`.
- Named volumes vs bind mounts: volumes live in Linux VM (fast inotify, portable); /mnt/c bind mounts break inotify + slow.
- Honest scope: lab-scale model of Cohesity ideas (DataProtect/FortKnox), not the product. Improvements: multi-site replication, real ML, RBAC, Alertmanager routing.
