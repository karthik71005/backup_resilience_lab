#!/bin/bash
# Unlock own restic repo (uses container env for repo/password).
export RESTIC_REPOSITORY="s3:http://minio:9000/backup-primary/${LAB_HOST:-app-server-2}"
restic unlock 2>&1 | tail -2
