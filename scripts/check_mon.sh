#!/bin/bash
curl -s 'http://localhost:9090/api/v1/query?query=up' | head -c 600
echo
curl -s -o /dev/null -w 'grafana:%{http_code}\n' http://localhost:3000/api/health
