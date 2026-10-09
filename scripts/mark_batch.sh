#!/bin/bash
# Mark historically-dirty snapshots suspect (prefix match).
for s in e8ddeda4 3aa9a97e 80d7f5e3 dda38289 d2c65780 c16df740 f4e238c1 a4345c73 753fe6a5 9b6641dc d1d6e60c 67c06012 dddcf54b bbafaa9e 99e2d80e; do
python3 -c "import sqlite3; c=sqlite3.connect('/var/lib/lab/state.db'); cur=c.execute(\"UPDATE snapshots SET status='suspect' WHERE id LIKE '$s%'\"); c.commit(); print('$s', cur.rowcount)"
done
echo done
