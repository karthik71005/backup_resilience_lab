"""Fault injection / clearing (spec Section 11). Testable file-based + container exec."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

FAULTS = ["disk_full", "dns_failure", "port_blocked", "permission_denied", "bad_credentials", "wrong_repo_password", "service_down"]

def _run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

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
        # backup resolv.conf then overwrite with unreachable nameserver
        try:
            data = Path("/etc/resolv.conf").read_bytes()
            Path("/tmp/resolv.conf.bak").write_bytes(data)
        except Exception:
            pass
        Path("/etc/resolv.conf").write_text("nameserver 192.0.2.1\noptions timeout:2 attempts:1\n")
        log.warning("fault_inject", "dns_failure resolv.conf overwritten")
        return {"fault": name}
    if name == "port_blocked":
        rc, out, err = _run(["iptables", "-A", "OUTPUT", "-p", "tcp", "--dport", "9000", "-j", "DROP"])
        if rc != 0:
            log.warning("fault_inject_fallback", f"iptables failed ({err.strip()[:200]}); use: docker network disconnect lab-net <container>")
            return {"fault": name, "fallback": "docker network disconnect", "rc": rc, "stderr": err.strip()[:500]}
        log.warning("fault_inject", "port_blocked iptables DROP 9000")
        return {"fault": name}
    if name == "permission_denied":
        target = Path(cfg.victim_dir) / "finance"
        target.mkdir(parents=True, exist_ok=True)
        os.chmod(target, 0o000)
        log.warning("fault_inject", f"permission_denied chmod 000 {target}")
        return {"fault": name, "path": str(target)}
    if name == "bad_credentials":
        Path("/tmp/lab_bad_creds").write_text("1")
        log.warning("fault_inject", "bad_credentials flag set (agent must override AWS_SECRET_ACCESS_KEY and restart to reproduce)")
        return {"fault": name, "hint": "set AWS_SECRET_ACCESS_KEY=wrong and restart agent"}
    if name == "wrong_repo_password":
        Path("/tmp/lab_bad_repo_pw").write_text("1")
        log.warning("fault_inject", "wrong_repo_password flag set (set RESTIC_PASSWORD=wrong and restart agent)")
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
            bak = Path("/tmp/resolv.conf.bak")
            if bak.exists():
                Path("/etc/resolv.conf").write_bytes(bak.read_bytes())
            out[n] = "cleared"
        elif n == "port_blocked":
            _run(["iptables", "-D", "OUTPUT", "-p", "tcp", "--dport", "9000", "-j", "DROP"])
            out[n] = "cleared (or reconnect network)"
        elif n == "permission_denied":
            target = Path(cfg.victim_dir) / "finance"
            try:
                os.chmod(target, 0o755)
            except Exception:
                pass
            out[n] = "cleared"
        elif n in ("bad_credentials", "wrong_repo_password"):
            Path(f"/tmp/lab_bad_{n}").unlink(missing_ok=True) if False else None
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
