"""Fault injection / clearing (spec Section 11). Testable file-based + container exec."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

FAULTS = ["disk_full", "dns_failure", "port_blocked", "permission_denied", "bad_credentials", "wrong_repo_password", "service_down"]

def _run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

IPT = ["sudo", "-n", "iptables"]  # least-priv: labuser may run only iptables via sudo (see Dockerfile)

def inject(name: str, cfg=None) -> dict:
    from .config import load_config
    from .logging_setup import get_logger
    cfg = cfg or load_config()
    log = get_logger("faults", log_dir=cfg.log_dir, host=cfg.host)
    if name == "disk_full":
        Path("/cache").mkdir(parents=True, exist_ok=True)
        rc, out, err = _run(["fallocate", "-l", "60M", "/cache/fill"])
        if rc != 0:  # fallback: dd
            rc, out, err = _run(["dd", "if=/dev/zero", "of=/cache/fill", "bs=1M", "count=60"])
        log.warning("fault_inject", f"disk_full rc={rc}", raw=err[-1000:])
        return {"fault": name, "rc": rc}
    if name == "dns_failure":
        # Primary: drop DNS egress (works where netfilter sees DNS).
        # Docker Desktop bypasses netfilter for its vsock DNS forwarder and
        # mounts resolv.conf/nsswitch.conf read-only, so there the effective
        # mechanism is host-side network disconnect (spec Section 11 fallback
        # spirit); both yield genuine lookup failures.
        rc1, _, err1 = _run(IPT + ["-A", "OUTPUT", "-p", "udp", "--dport", "53", "-j", "DROP"])
        rc2, _, err2 = _run(IPT + ["-A", "OUTPUT", "-p", "tcp", "--dport", "53", "-j", "DROP"])
        host_cmd = "docker network disconnect backup-resilience-lab_lab-net <container>"
        if rc1 != 0 or rc2 != 0:
            log.warning("fault_inject_fallback", f"iptables DNS block failed; host fallback: {host_cmd}")
            return {"fault": name, "mechanism": "host", "host_cmd": host_cmd}
        ok = _run(["getent", "hosts", "minio"])
        if ok[0] == 0:
            log.warning("fault_inject_fallback", f"iptables DNS block ineffective here (resolver bypasses netfilter); host fallback: {host_cmd}")
            return {"fault": name, "mechanism": "host", "host_cmd": host_cmd, "note": "iptables rules installed but resolution still works"}
        log.warning("fault_inject", "dns_failure iptables DROP 53/udp+tcp")
        return {"fault": name, "mechanism": "iptables"}
    if name == "port_blocked":
        rc, out, err = _run(IPT + ["-A", "OUTPUT", "-p", "tcp", "--dport", "9000", "-j", "DROP"])
        host_cmd = "docker network disconnect backup-resilience-lab_lab-net <container>"
        if rc != 0:
            log.warning("fault_inject_fallback", f"iptables failed ({err.strip()[:200]}); host fallback: {host_cmd}")
            return {"fault": name, "mechanism": "host", "host_cmd": host_cmd}
        probe = _run(["curl", "-s", "-m", "4", "http://minio:9000/minio/health/live"])
        if probe[0] == 0:
            log.warning("fault_inject_fallback", f"iptables 9000 DROP ineffective here; host fallback: {host_cmd}")
            return {"fault": name, "mechanism": "host", "host_cmd": host_cmd, "note": "rule installed but port still reachable"}
        log.warning("fault_inject", "port_blocked iptables DROP 9000")
        return {"fault": name, "mechanism": "iptables"}
    if name == "permission_denied":
        target = Path(cfg.victim_dir) / "finance"
        target.mkdir(parents=True, exist_ok=True)
        os.chmod(target, 0o000)
        log.warning("fault_inject", f"permission_denied chmod 000 {target}")
        return {"fault": name, "path": str(target)}
    if name == "bad_credentials":
        Path("/tmp/lab_bad_creds").write_text("1")
        log.warning("fault_inject", "bad_credentials flag set (backup runs now use a wrong S3 secret until cleared)")
        return {"fault": name}
    if name == "wrong_repo_password":
        Path("/tmp/lab_bad_repo_pw").write_text("1")
        log.warning("fault_inject", "wrong_repo_password flag set (backup runs now use a wrong restic password until cleared)")
        return {"fault": name}
    if name == "service_down":
        log.warning("fault_inject", "service_down: run `docker compose stop minio` from host")
        return {"fault": name, "hint": "docker compose stop minio"}
    raise SystemExit(f"unknown fault {name}; choose from {FAULTS}")

def clear(name: str = "all", cfg=None) -> dict:
    from .config import load_config
    from .logging_setup import get_logger
    cfg = cfg or load_config()
    log = get_logger("faults", log_dir=cfg.log_dir, host=cfg.host)
    names = FAULTS if name in ("all", "--all") else [name]
    out = {}
    for n in names:
        if n == "disk_full":
            try:
                Path("/cache/fill").unlink(missing_ok=True)
            except TypeError:
                if Path("/cache/fill").exists():
                    Path("/cache/fill").unlink()
            out[n] = "cleared"
        elif n == "dns_failure":
            _run(IPT + ["-D", "OUTPUT", "-p", "udp", "--dport", "53", "-j", "DROP"])
            _run(IPT + ["-D", "OUTPUT", "-p", "tcp", "--dport", "53", "-j", "DROP"])
            # also restore resolv.conf if an older inject overwrote it
            bak = Path("/tmp/resolv.conf.bak")
            if bak.exists():
                try:
                    Path("/etc/resolv.conf").write_bytes(bak.read_bytes())
                except Exception:
                    pass
            out[n] = "cleared"
        elif n == "port_blocked":
            _run(IPT + ["-D", "OUTPUT", "-p", "tcp", "--dport", "9000", "-j", "DROP"])
            out[n] = "cleared (or reconnect network)"
        elif n == "permission_denied":
            target = Path(cfg.victim_dir) / "finance"
            try:
                os.chmod(target, 0o755)
            except Exception:
                pass
            out[n] = "cleared"
        elif n in ("bad_credentials", "wrong_repo_password"):
            for f in ["/tmp/lab_bad_creds", "/tmp/lab_bad_repo_pw"]:
                try:
                    Path(f).unlink()
                except Exception:
                    pass
            out[n] = "cleared"
        elif n == "service_down":
            out[n] = "run `docker compose up -d minio` from host"
        log.info("fault_clear", f"{n}: {out[n]}")
    return out
