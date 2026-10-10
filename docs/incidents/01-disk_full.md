# 01-disk_full: restic scratch space exhausted

## Summary
Scheduled backup on app-server-1 failed its preflight check: the /cache
tmpfs (64 MB, shared by restic cache and temp) had 3.6 MB free against a
10 MB minimum after a 60 MB stray file filled it. Triage: STORAGE_DISK_FULL,
P2, self-resolve with runbook.

## Timeline (UTC, 2026-10-10)
- 15:4x `lab fault inject disk_full` → `fallocate -l 60M /cache/fill` (rc=0)
- `df -h /cache`: 64M total, 61M used, 3.6M avail (95%)
- `lab backup run` → `{"ok": false, "exit_code": 28}` in ~0s (preflight refusal)
- `lab triage analyze` → STORAGE_DISK_FULL / storage / P2
- `lab case create` → CASE-20261010-001
- `lab fault clear disk_full` → /cache/fill removed; next backup healthy (301 files)

## Symptoms and exact log lines
`backup.jsonl`:
```json
{"level": "ERROR", "event": "backup_failed", "message": "no space left on device: /cache has 3.6MB free, need 10MB", "exit_code": 28}
```

## Diagnosis steps
1. `df -h /cache` → 95% used; `ls -la /cache` → 60 MB `fill` file + restic cache dir.
2. `du -sh /cache/*` identifies the stray file (not restic growth).
3. Confirm jobs failing at preflight, not mid-write (exit 28, duration ~0s).

## Root cause
Stray 60 MB file on the 64 MB /cache tmpfs. (Lab note: at this data
scale restic itself tolerates 95% pressure, so the agent gates on free
space before starting — real agents do the same; see ARCHITECTURE.md.)

## Resolution
`lab fault clear disk_full` (removes /cache/fill); reran backup → ok.

## Prevention
- Alert on `node_filesystem_avail_bytes{mountpoint="/cache"}` < 10 MB.
- Cap restic cache size; cron tmp cleanup; bigger tmpfs in prod.

## Customer-facing update
Backups were paused because the worker's temporary disk filled up. We
cleared the stray data, confirmed free space, and the next scheduled
backup completed normally. No backup data was lost.
