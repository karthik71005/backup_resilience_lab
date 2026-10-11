"""Typer CLI: `lab ...` (spec Section 12)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
import typer

from .config import load_config

app = typer.Typer(help="Backup Resilience Lab")
triage_app = typer.Typer(help="Triage failure logs")
case_app = typer.Typer(help="Support cases")
fault_app = typer.Typer(help="Fault injection")
backup_app = typer.Typer(help="Backup ops")
vault_app = typer.Typer(help="Vault ops")
detector_app = typer.Typer(help="Detector ops")
attack_app = typer.Typer(help="Attack simulator (guarded)")
app.add_typer(triage_app, name="triage")
app.add_typer(case_app, name="case")
app.add_typer(fault_app, name="fault")
app.add_typer(backup_app, name="backup")
app.add_typer(vault_app, name="vault")
app.add_typer(detector_app, name="detector")
app.add_typer(attack_app, name="attack")

@app.command()
def seed(count: int = 300, victim: Optional[str] = None):
    cfg = load_config()
    from .seed import seed_data
    res = seed_data(victim or cfg.victim_dir, count=count)
    print(json.dumps(res))

@attack_app.command("run")
def attack_run(rate: Optional[float] = None, delay: Optional[float] = None):
    cfg = load_config()
    from .simulator import run_attack
    print(json.dumps(run_attack(cfg, rate=rate, delay=delay), indent=2))

@backup_app.command("run")
def backup_run():
    from .backup import run_backup
    print(json.dumps(run_backup(), indent=2, default=str))

@backup_app.command("loop")
def backup_loop():
    from .backup import loop
    loop()

@backup_app.command("resume")
def backup_resume():
    """Unpause scheduled backups after an alert has been handled (verify + restore first)."""
    cfg = load_config()
    from . import state as st
    from .logging_setup import get_logger
    st.set_paused(cfg.state_db, False)
    get_logger("backup", log_dir=cfg.log_dir, host=cfg.host).warning("backups_resumed", "operator resumed scheduled backups")
    try:
        from .exporter import set_paused
        set_paused(False)
    except Exception:
        pass
    print("backups resumed")

@app.command()
def snapshots(host: Optional[str] = None, limit: int = 20):
    """List recent snapshots for a host (newest first)."""
    cfg = load_config()
    from . import state as st
    rows = st.list_snapshots(cfg.state_db, host or cfg.host)
    rows = sorted(rows, key=lambda r: r.get("taken_at", ""), reverse=True)[:limit]
    print(json.dumps([{"id": r["id"][:8], "taken_at": r["taken_at"], "status": r["status"],
                       "files": r["files"], "bytes": r["bytes"]} for r in rows], indent=2))

@vault_app.command("status")
def vault_status():
    from .vault import vault_status as vs
    print(json.dumps(vs(), indent=2, default=str))

@vault_app.command("try-delete")
def vault_try_delete(key: Optional[str] = None):
    from .vault import vault_try_delete as vtd
    print(json.dumps(vtd(key=key), indent=2, default=str))

@detector_app.command("run")
def detector_run():
    from .detector import Detector
    Detector().run()

@detector_app.command("tune")
def detector_tune(logfile: Optional[str] = None):
    """Replay recorded event logs and print precision/recall."""
    import json as _json
    from .detector import tune
    print(_json.dumps(tune(), indent=2))

@app.command()
def restore(latest_clean: bool = typer.Option(False, "--latest-clean"),
            host: Optional[str] = None,
            snapshot: Optional[str] = None):
    cfg = load_config()
    from .restore import run_restore
    run_restore(cfg, host=host or cfg.host, latest_clean=latest_clean or snapshot is None, snapshot_id=snapshot)

@fault_app.command("inject")
def fault_inject(name: str):
    from .faults import inject
    print(json.dumps(inject(name), indent=2, default=str))

@fault_app.command("clear")
def fault_clear(name: Optional[str] = typer.Argument("all"),
                all: bool = typer.Option(False, "--all", help="Clear all faults")):
    from .faults import clear
    target = "all" if (all or name in ("all", "--all")) else name
    print(json.dumps(clear(target), indent=2, default=str))

@triage_app.command("analyze")
def triage_analyze(logfile: str, since: Optional[str] = None):
    from .triage import analyze
    from rich.table import Table
    from rich.console import Console
    res = analyze(logfile, since=since)
    console = Console()
    table = Table(title=f"Triage {logfile} ({res['failures']} failures)")
    table.add_column("Rule"); table.add_column("Category"); table.add_column("Sev"); table.add_column("Count"); table.add_column("Fix")
    for gid, g in res["groups"].items():
        table.add_row(gid, g["rule"].get("category", ""), g["rule"].get("severity", ""), str(g["count"]), str(g["rule"].get("fix", ""))[:60])
    console.print(table)
    print(json.dumps({k: (str(v)[:500] if not isinstance(v, (dict, int)) else v) for k, v in res.items() if k != "groups"}, indent=2))

@case_app.command("create")
def case_create(logfile: str):
    from .triage import analyze
    from .cases import create_case
    cfg = load_config()
    res = analyze(logfile)
    cases = create_case(res, out_dir="cases", db_path=cfg.state_db, cfg=cfg)
    for c in cases:
        print(f"{c['id']} [{c['severity']}/{c['category']}] {c['title']} -> cases/{c['id']}.md")

@case_app.command("list")
def case_list():
    for p in sorted(Path("cases").glob("CASE-*.json")):
        d = json.loads(p.read_text())
        print(f"{d['id']} [{d['severity']}/{d['category']}] {d['title']}")

@case_app.command("show")
def case_show(case_id: str):
    p = Path(f"cases/{case_id}.md")
    if not p.exists():
        p = Path(f"cases/{case_id}.json")
    print(p.read_text() if p.exists() else f"not found: {case_id}")

@app.command()
def exporter(port: int = 8000):
    from .exporter import serve
    serve(port)

if __name__ == "__main__":
    app()
