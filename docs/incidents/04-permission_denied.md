# 04-permission_denied: agent cannot read finance directory

## Summary
Backup on app-server-1 failed with exit 3 after `/data/victim/finance`
was chmodded 000 (agent runs as non-root labuser). The manifest walk
recorded the unreadable subtree and the failure was enriched with the
exact path. Triage: PERMISSIONS, P2, self-resolve.

## Timeline (UTC, 2026-10-10)
- `lab fault inject permission_denied` → `chmod 000 /data/victim/finance`
- `lab backup run` → exit 3, scan+archival errors for finance
- `lab triage analyze` → PERMISSIONS / permissions / P2
- `lab case create` → CASE-20261010-004
- `lab fault clear permission_denied` → chmod 755; backup healthy (301 files)

## Symptoms and exact log lines
```json
{"level": "ERROR", "event": "backup_failed", "message": "restic backup failed after 4.6s. permission denied: victim/finance", "exit_code": 3}
```

## Diagnosis steps
1. `ls -l /data/victim` → `d--------- finance` stands out.
2. `namei -l /data/victim/finance` → pinpoints the mode break.
3. `id labuser` → confirms non-root; sudo-run read succeeds → ownership/mode, not ACL/SELinux.

## Root cause
Directory mode 000 removed owner read/execute. (Lab note: restic --json
errors omit the human-readable cause, so the agent enriches failures
from its own manifest walk, which probes every directory. Incomplete
snapshots are recorded as suspect, never clean.)

## Resolution
Restored mode 755; reran full backup → ok.

## Prevention
- Pre-backup readability probe (already in manifest builder).
- Alert on `permissions`-category failures; audit chmod automation.

## Customer-facing update
One backup did not finish because the worker lost read access to part of
the data. We restored access and completed a full verified backup. No
files were lost.
