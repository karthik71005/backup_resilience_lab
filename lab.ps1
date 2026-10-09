param([Parameter(ValueFromRemainingArguments=$true)]$Args)
wsl -d Ubuntu-24.04 -- bash -lc "cd ~/projects/backup-resilience-lab && make $Args"
