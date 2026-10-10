# 06-wrong_repo_password: wrong restic repository password

## Summary
Backup on app-server-1 failed key unlock after a wrong RESTIC_PASSWORD
was injected via flag file. Triage: AUTH_REPO_PASSWORD, P2, L2 secrets
handling.

## Timeline (UTC, 2026-10-10)
- `lab fault inject wrong_repo_password` → /tmp/lab_bad_repo_pw flag
- `lab backup run` → exit 1, `wrong password or no key found`
- `lab triage analyze` → AUTH_REPO_PASSWORD / auth / P2
- `lab case create` → CASE-20261010-006
- `lab fault clear wrong_repo_password`; backup healthy

## Symptoms and exact log lines
```
Fatal: wrong password or no key found
```

## Diagnosis steps
1. `env | grep RESTIC_PASSWORD` → compare against secret store; recent rotation?
2. `restic snapshots` with candidate password → binary ok/wrong test.
3. Check for repo re-init accidents (new password = new key set, old snapshots unreadable).

## Root cause
Wrong repository password active for the agent (simulated rotation miss).

## Resolution
Restored correct RESTIC_PASSWORD from vault; backup ok; snapshots readable.

## Prevention
- Password changes via orchestrated rotation with verification read-back.
- Keep offline key escrow; alert on `auth`-category failures.

## Customer-facing update
Backups failed because the worker had the wrong encryption password for
the backup store. We restored the correct password and verified backups
are running again. Stored backups were never at risk.
