#!/bin/bash
for s in bf5af296 b74585bc 6ee7098f; do
python3 /tmp/ms_one.py "$s"
done
echo done
