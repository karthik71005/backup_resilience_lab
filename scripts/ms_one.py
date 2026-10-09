import sqlite3, sys
c = sqlite3.connect("/var/lib/lab/state.db")
cur = c.execute("UPDATE snapshots SET status='suspect' WHERE id LIKE ?", (sys.argv[1] + "%",))
c.commit()
print(sys.argv[1], cur.rowcount)
