# 05-bad_credentials: wrong S3 secret key

## Summary
Backup on app-server-1 failed signature verification after a wrong
AWS_SECRET_ACCESS_KEY was injected via flag file. Triage: AUTH_S3, P2,
auth runbook.

## Timeline (UTC, 2026-10-10)
- `lab fault inject bad_credentials` → /tmp/lab_bad_creds flag (backup runs use wrong secret)
- `lab backup run` → exit 1, SignatureDoesNotMatch prose
- `lab triage analyze` → AUTH_S3 / auth / P2 (after rule refinement, see below)
- `lab case create` → CASE-20261010-005
- `lab fault clear bad_credentials` → flag removed; backup healthy

## Symptoms and exact log lines
```
Fatal: unable to open config file: Stat: The request signature we calculated does not match the signature you provided. Check your AWS secret access key and signing method.
```

## Diagnosis steps
1. `env | grep -i aws` inside agent → secret mismatch vs vault.
2. Same request with correct secret succeeds → key problem, not clock skew (also check `date -u`; >5 min skew breaks SigV4).
3. `mc alias list` / admin console confirms key rotation state.

## Root cause
Wrong S3 secret active for the agent. (Lab note: RustFS returns SigV4
failure as prose, not the `SignatureDoesNotMatch` XML code, so the
AUTH_S3 rule was extended with `signature.*does not match` /
`check your AWS secret access key` after observing the real text.)

## Resolution
Restored correct secret (flag cleared); backup ok.

## Prevention
- Secrets from vault agent with rotation; alert on `auth`-category failures.
- Separate keys per host for blast-radius control.

## Customer-facing update
Backups failed because the worker used an outdated storage password. We
corrected it and confirmed backups are succeeding again. Your stored
backups were unaffected.
