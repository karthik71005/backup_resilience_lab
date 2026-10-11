"""Demo console backend (stdlib only). Runs on the WSL host:
serves dashboard/index.html on :8080 and drives the lab via
`docker compose exec` + host triage. No new dependencies.

Usage:  make dashboard   (or: python3 dashboard/app.py [port])
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
CTR = "backup-resilience-lab-app-server-1-1"
NET = "backup-resilience-lab_lab-net"

LONG_TIMEOUT = 300


def run(args, timeout=60, cwd=REPO):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def cexec(*cli, timeout=60):
    return run(["docker", "compose", "exec", "-T", "app-server-1",
                "python3", "-m", "lab.cli", *cli], timeout=timeout)


def prom_query(expr):
    try:
        with urllib.request.urlopen(
                "http://localhost:9090/api/v1/query?query=" + expr, timeout=10) as r:
            vals = json.load(r)["data"]["result"]
            return {v["metric"].get("host", "?"): v["value"][1] for v in vals}
    except Exception:
        return {}


def metrics_text():
    try:
        with urllib.request.urlopen("http://localhost:8001/metrics", timeout=10) as r:
            return r.read().decode()
    except Exception:
        return ""


def gauge(text, name, labels=""):
    for line in text.splitlines():
        if line.startswith(name + "{") and (not labels or labels in line):
            try:
                return float(line.rsplit(" ", 1)[1])
            except Exception:
                pass
    return None


def overview():
    m = metrics_text()
    rc, snaps = cexec("snapshots", "--host", "app-server-1", "--limit", "8")
    try:
        snap_list = json.loads(snaps) if rc == 0 else []
    except Exception:
        snap_list = []
    rc2, ls = run(["docker", "compose", "exec", "-T", "app-server-1",
                   "ls", "/data/victim"], timeout=30)
    victim_files = len([l for l in ls.splitlines() if l.strip()]) if rc2 == 0 else -1
    return {
        "score": gauge(m, "lab_detector_score", 'host="app-server-1"'),
        "paused": gauge(m, "lab_backups_paused", 'host="app-server-1"'),
        "alerts": prom_query("lab_alerts_total"),
        "clean": gauge(m, "lab_snapshots_total", 'status="clean"'),
        "suspect": gauge(m, "lab_snapshots_total", 'status="suspect"'),
        "rto": gauge(m, "lab_last_restore_rto_seconds", 'host="app-server-1"'),
        "last_success": gauge(m, "lab_backup_last_success_timestamp", 'host="app-server-1"'),
        "snapshots": snap_list,
        "victim_entries": victim_files,
    }


class H(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
        except Exception:
            n = 0
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            p = os.path.join(REPO, "dashboard", "index.html")
            with open(p, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/overview":
            try:
                return self._send({"ok": True, "overview": overview()})
            except Exception as e:
                return self._send({"ok": False, "error": str(e)[:500]}, 500)
        if self.path == "/api/vault":
            _, st = cexec("vault", "status", timeout=60)
            _, td = cexec("vault", "try-delete", timeout=60)
            return self._send({"ok": True, "status": st[-3000:], "try_delete": td[-2000:]})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/upload":
            # multipart body must be parsed by the upload handler itself;
            # do NOT pre-read it here.
            try:
                return self._upload()
            except Exception as e:
                return self._send({"ok": False, "error": str(e)[:500]}, 500)
        try:
            data = json.loads(self._body() or b"{}")
        except Exception:
            data = {}
        try:
            if self.path == "/api/backup":
                rc, out = cexec("backup", "run", timeout=LONG_TIMEOUT)
                return self._send({"ok": rc == 0, "output": out[-4000:]})
            if self.path == "/api/attack":
                rc, out = cexec("attack", "run", "--rate", "15", timeout=LONG_TIMEOUT)
                return self._send({"ok": rc == 0, "output": out[-4000:]})
            if self.path == "/api/restore":
                rc, out = cexec("restore", "--latest-clean", "--host", "app-server-1",
                                timeout=LONG_TIMEOUT)
                return self._send({"ok": rc == 0, "output": out[-5000:]})
            if self.path == "/api/resume":
                rc, out = cexec("backup", "resume", timeout=60)
                return self._send({"ok": rc == 0, "output": out[-1000:]})
            if self.path == "/api/fault":
                return self._fault(data.get("name", ""))
            if self.path == "/api/clear":
                return self._clear()
            if self.path == "/api/triage":
                return self._triage()
        except subprocess.TimeoutExpired:
            return self._send({"ok": False, "error": "timed out"}, 504)
        except Exception as e:
            return self._send({"ok": False, "error": str(e)[:500]}, 500)
        self.send_response(404)
        self.end_headers()

    def _upload(self):
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype or "boundary=" not in ctype:
            return self._send({"ok": False, "error": "need multipart/form-data"}, 400)
        try:
            n = int(self.headers.get("Content-Length", 0))
        except Exception:
            n = 0
        if n <= 0 or n > 50 * 1024 * 1024:
            return self._send({"ok": False, "error": "bad length"}, 400)
        body = self.rfile.read(n)
        bnd = ctype.split("boundary=")[1].strip().strip('"').encode()
        parts = body.split(b"--" + bnd)
        found = None
        for p in parts:
            if b'Content-Disposition' in p and b'filename="' in p:
                fn = p.split(b'filename="', 1)[1].split(b'"', 1)[0].decode("utf-8", "replace")
                payload = p.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
                found = (os.path.basename(fn).replace("/", "_"), payload)
                break
        if not found or not found[0]:
            return self._send({"ok": False, "error": "no file field"}, 400)
        name, payload = found
        tmp = os.path.join(tempfile.gettempdir(), "lab-upload-" + name)
        with open(tmp, "wb") as f:
            f.write(payload)
        size = os.path.getsize(tmp)
        rc, out = run(["docker", "cp", tmp,
                       CTR + ":/data/victim/" + name], timeout=60)
        os.unlink(tmp)
        if rc != 0:
            return self._send({"ok": False, "error": out[-1000:]}, 500)
        return self._send({"ok": True, "name": name, "size": size,
                           "note": "staged at /data/victim/ — press Backup now"})

    def _fault(self, name):
        if name not in ("disk_full", "dns_failure", "port_blocked",
                        "permission_denied", "bad_credentials",
                        "wrong_repo_password", "service_down"):
            return self._send({"ok": False, "error": "unknown fault"}, 400)
        rc, out = cexec("fault", "inject", name, timeout=60)
        extra = ""
        if name == "dns_failure":
            _, extra = run(["docker", "network", "disconnect", NET, CTR], timeout=60)
        if name == "service_down":
            _, extra = run(["docker", "compose", "stop", "minio"], timeout=120)
        # run one backup to materialise the failure
        rc2, bout = cexec("backup", "run", timeout=LONG_TIMEOUT)
        return self._send({"ok": True, "inject": out[-1500:], "host_step": extra[-500:],
                           "backup": bout[-2500:]})

    def _clear(self):
        rc, out = cexec("fault", "clear", "--all", timeout=60)
        run(["docker", "network", "connect", NET, CTR], timeout=60)
        run(["docker", "compose", "up", "-d", "minio"], timeout=180)
        return self._send({"ok": True, "output": out[-2000:]})

    def _triage(self):
        from lab.triage import analyze
        rc, out = run(["docker", "compose", "exec", "-T", "app-server-1",
                       "tail", "-30", "/var/log/lab/backup.jsonl"], timeout=60)
        tmp = os.path.join(tempfile.gettempdir(), "lab-dash-triage.jsonl")
        with open(tmp, "w") as f:
            f.write(out)
        res = analyze(tmp)
        groups = {gid: {"category": g["rule"].get("category"),
                        "severity": g["rule"].get("severity"),
                        "count": g["count"], "fix": g["rule"].get("fix"),
                        "cause": g["rule"].get("cause")}
                  for gid, g in res["groups"].items()}
        return self._send({"ok": True, "failures": res["failures"], "groups": groups})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print(f"[dashboard] http://localhost:{port}  (repo: {REPO})")
    srv.serve_forever()
