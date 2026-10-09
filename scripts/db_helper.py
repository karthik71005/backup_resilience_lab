"""DB helper for ops (runs inside agent container): mark suspect, unpause, list."""
import sqlite3
import sys

db = "/var/lib/lab/state.db"

def main():
    cmd = sys.argv[1]
    c = sqlite3.connect(db)
    if cmd == "mark-suspect":
        snap = sys.argv[2]
        c.execute("UPDATE snapshots SET status='suspect' WHERE id=?", (snap,))
        c.commit()
        print(f"marked suspect: {snap}")
    elif cmd == "unpause":
        c.execute("INSERT OR REPLACE INTO kv(key,value) VALUES('backups_paused','false')")
        c.commit()
        print("unpaused")
    elif cmd == "list":
        host = sys.argv[2] if len(sys.argv) > 2 else "app-server-1"
        for r in c.execute("SELECT substr(id,1,8), taken_at, status, files FROM snapshots WHERE host=? ORDER BY taken_at", (host,)):
            print(r)
    elif cmd == "score":
        r = c.execute("SELECT value FROM kv WHERE key='detector_score'").fetchone()
        print("detector_score:", r[0] if r else None)
        r = c.execute("SELECT value FROM kv WHERE key='alerts_total'").fetchone()
        print("alerts_total:", r[0] if r else None)
        r = c.execute("SELECT value FROM kv WHERE key='backups_paused'").fetchone()
        print("backups_paused:", r[0] if r else None)
    c.close()

main()
