# Recovery results (spec Section 9) — every row from an actual run. Do not fabricate.

Summary over 5 runs (app-server-1, 301 files each): detection latency median
9.88 s (6.62–10.23), RPO 12.6–23.3 s, RTO 1.24–2.43 s, success 100% every run.

| Date (UTC) | Commit | Host | Detection latency (s) | RPO (s) | RTO (s) | Success % | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-09T17:52:35Z | 4edbab0 | app-server-1 | 9.95 | 23.26 | 1.48 | 100.0 | run 1: attack 17:44:52.498Z, detected 17:45:02.448Z (score 0.60), restored snap 9d33de18 (taken 17:44:29Z, 301 files) |
| 2026-10-10T14:41:00Z | 4edbab0 | app-server-1 | 6.62 | 12.59 | 2.43 | 100.0 | run 2: attack 2026-10-09T17:55:01.744Z, detected 17:55:08.360Z (score 0.58), restored snap f22099cc (taken 17:54:49Z, 301 files); restore re-run post-restart with latest-match fix |
| 2026-10-10T14:44:00Z | 4edbab0 | app-server-1 | 7.94 | 19.34 | 2.35 | 100.0 | run 3: attack 14:42:41.010Z, detected 14:42:48.946Z (score 0.59), restored snap adc881ce (301 files) |
| 2026-10-10T14:46:00Z | 4edbab0 | app-server-1 | 10.23 | 22.63 | 2.08 | 100.0 | run 4: attack 14:44:34.823Z, detected 14:44:45.049Z (score 0.60), restored snap beb09149 (301 files) |
| 2026-10-10T14:47:00Z | 4edbab0 | app-server-1 | 9.88 | 12.94 | 1.24 | 100.0 | run 5: attack 14:46:10.185Z, detected 14:46:20.068Z (score 0.61), restored snap ac52d35b (301 files) |
