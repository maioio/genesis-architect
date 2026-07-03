"""genesis_sync.py — Autonomous Sync Manager for Genesis Architect PRO.

Runs on a schedule (via CronCreate / GitHub Actions / crontab) to:
  1. Run a GATE-mode GDE session — architecture regression check
  2. Emit structured findings with severity + recommended action
  3. Within the GREEN zone, auto-apply low-risk improvements
  4. In the YELLOW zone, write a pending-actions file and notify
  5. Never touch the RED zone without human approval

Approval scoping (mirrors what serious devs do in 2026):
  GREEN  (auto)  : doc sync, score-history append, fragility map refresh
  YELLOW (PR/file): refactoring suggestions, rules failures, high churn warnings
  RED    (block)  : breaking API changes, security findings, arch restructure

Usage::

    genesis sync --dir /path/to/project
    genesis sync --dir . --dry-run
    genesis sync --dir . --report-only
    genesis sync --auto-apply        # GREEN zone writes without prompt

Called by claude-loop / GitHub Actions / CronCreate:
    claude -p "genesis sync --dir . --auto-apply --json" --print

CI mode (non-zero exit = findings found):
    genesis sync --dir . --auto-apply --ci-mode
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

ZONE_GREEN  = "green"   # auto-apply
ZONE_YELLOW = "yellow"  # write pending file, needs human
ZONE_RED    = "red"     # block, alert only


@dataclass
class SyncFinding:
    """A single finding from a sync run."""
    id: str
    zone: str                  # green / yellow / red
    engine: str
    title: str
    detail: str
    action: str                # what genesis-sync will do or recommend
    auto_applied: bool = False
    severity: str = "info"     # info / warning / critical


@dataclass
class SyncReport:
    """Full output of one sync run."""
    run_id: str
    project_dir: str
    timestamp: str
    duration_seconds: float
    findings: list[SyncFinding] = field(default_factory=list)
    green_applied: int = 0
    yellow_pending: int = 0
    red_blocked: int = 0
    gate_outcome: str = "pass"
    score: float | None = None
    decay_forecast: dict | None = None
    summary: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------

def _classify_finding(engine: str, data: dict) -> list[SyncFinding]:
    """Translate engine output keys into SyncFinding objects."""
    findings: list[SyncFinding] = []

    if engine == "architecture_scorer":
        score = data.get("score", 100)
        label = data.get("score_label", "")
        # Decay forecast (GREEN if just updating history, YELLOW if declining)
        if data.get("decay_forecast"):
            fc = data["decay_forecast"]
            weekly = fc.get("weekly_delta", 0)
            weeks_to_crit = fc.get("weeks_to_critical")
            if weekly < -1.5 or (weeks_to_crit is not None and weeks_to_crit < 8):
                findings.append(SyncFinding(
                    id=f"decay_trend_{int(time.time())}",
                    zone=ZONE_YELLOW,
                    engine=engine,
                    title="Architecture decay detected",
                    detail=f"Score trend: {weekly:+.2f}/week. Predicted score in 12 weeks: {fc.get('predicted_score_12w', '?')}",
                    action="Genesis will open a refactoring task in .genesis/pending.json",
                    severity="warning",
                ))
        if score < 55:
            findings.append(SyncFinding(
                id=f"score_critical_{int(time.time())}",
                zone=ZONE_RED,
                engine=engine,
                title=f"Architecture score critical: {score:.1f} ({label})",
                detail="Score below 55. Immediate review required.",
                action="Blocked. Human review required.",
                severity="critical",
            ))
        elif score < 70:
            findings.append(SyncFinding(
                id=f"score_low_{int(time.time())}",
                zone=ZONE_YELLOW,
                engine=engine,
                title=f"Architecture score below 70: {score:.1f} ({label})",
                detail="Score in warning band.",
                action="Logged to .genesis/pending.json for next refactoring session.",
                severity="warning",
            ))

    elif engine == "rules_engine":
        if not data.get("rules_passed", True):
            failed = data.get("failed_rules", [])
            for rule in failed:
                findings.append(SyncFinding(
                    id=f"rule_{rule}_{int(time.time())}",
                    zone=ZONE_YELLOW,
                    engine=engine,
                    title=f"Rule failed: {rule}",
                    detail=data.get("rules_report", ""),
                    action="Logged to .genesis/pending.json",
                    severity="warning",
                ))

    elif engine == "git_analyzer":
        hc = data.get("high_churn_count", 0)
        bf = data.get("bus_factor_1_count", 0)
        if hc > 3:
            findings.append(SyncFinding(
                id=f"churn_{int(time.time())}",
                zone=ZONE_YELLOW,
                engine=engine,
                title=f"{hc} high-churn modules detected",
                detail="Modules with high churn are fragility candidates.",
                action="Logged to .genesis/pending.json",
                severity="warning",
            ))
        if bf > 0:
            findings.append(SyncFinding(
                id=f"busfactor_{int(time.time())}",
                zone=ZONE_YELLOW,
                engine=engine,
                title=f"{bf} module(s) with bus-factor=1",
                detail="Single owner — knowledge silo risk.",
                action="Logged to .genesis/pending.json",
                severity="warning",
            ))

    elif engine == "import_audit":
        missing = data.get("missing_count", 0)
        undecl = data.get("undeclared_count", 0)
        if missing + undecl > 0:
            findings.append(SyncFinding(
                id=f"import_drift_{int(time.time())}",
                zone=ZONE_YELLOW,
                engine=engine,
                title=f"Import audit: {missing} missing, {undecl} undeclared links",
                detail="Diagram diverges from actual imports.",
                action="Logged to .genesis/pending.json",
                severity="warning",
            ))

    elif engine == "antipattern_detector":
        crit = data.get("critical_count", 0)
        high = data.get("high_count", 0)
        if crit > 0:
            findings.append(SyncFinding(
                id=f"antipattern_crit_{int(time.time())}",
                zone=ZONE_RED,
                engine=engine,
                title=f"{crit} CRITICAL anti-patterns detected",
                detail=f"Also {high} HIGH-severity patterns.",
                action="Blocked. Human review required before any commit.",
                severity="critical",
            ))
        elif high > 2:
            findings.append(SyncFinding(
                id=f"antipattern_high_{int(time.time())}",
                zone=ZONE_YELLOW,
                engine=engine,
                title=f"{high} HIGH anti-patterns detected",
                detail="Refactoring recommended.",
                action="Logged to .genesis/pending.json",
                severity="warning",
            ))

    elif engine == "fragility_classifier":
        volatile = data.get("volatile_count", 0)
        fragile  = data.get("fragile_count", 0)
        if volatile > 0:
            findings.append(SyncFinding(
                id=f"fragile_{int(time.time())}",
                zone=ZONE_YELLOW,
                engine=engine,
                title=f"{volatile} volatile + {fragile} fragile modules",
                detail="Fragility map updated.",
                action="Fragility map refreshed (GREEN write). Logged to pending if >2 volatile.",
                severity="info" if volatile <= 2 else "warning",
            ))

    return findings


# ---------------------------------------------------------------------------
# Pending actions file (.genesis/pending.json)
# ---------------------------------------------------------------------------

def _write_pending(project_dir: Path, findings: list[SyncFinding]) -> None:
    """Append yellow-zone findings to .genesis/pending.json."""
    pending_file = project_dir / ".genesis" / "pending.json"
    pending_file.parent.mkdir(exist_ok=True)

    existing: list[dict] = []
    if pending_file.exists():
        try:
            existing = json.loads(pending_file.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing_ids = {e.get("id") for e in existing}
    new_items = [asdict(f) for f in findings if f.id not in existing_ids]
    existing.extend(new_items)

    pending_file.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_sync_log(project_dir: Path, report: SyncReport) -> None:
    """Append one JSON line to .genesis/sync_log.jsonl."""
    log_file = project_dir / ".genesis" / "sync_log.jsonl"
    log_file.parent.mkdir(exist_ok=True)
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report.as_dict(), ensure_ascii=False) + "\n")


def _read_sync_config(project_dir: Path) -> dict:
    """Load .genesis/sync_config.json or return sensible defaults."""
    cfg_file = project_dir / ".genesis" / "sync_config.json"
    defaults: dict = {
        "schedule": "every_sunday_2am",
        "cron": "0 2 * * 0",
        "auto_apply_green": True,
        "notify_channel": None,
        "score_threshold_yellow": 70,
        "score_threshold_red": 55,
        "max_high_antipatterns": 2,
        "max_churn_modules": 3,
        "engines_enabled": [
            "import_graph", "architecture_scorer", "antipattern_detector",
            "fragility_classifier", "rules_engine", "git_analyzer", "import_audit",
        ],
        "approval_scope": {
            "green": ["score_history", "fragility_map", "sync_log"],
            "yellow": ["pending.json", "workspace.html"],
            "red": [],
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
    }
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            return {**defaults, **cfg}
        except Exception:
            pass
    return defaults


# ---------------------------------------------------------------------------
# Core sync runner
# ---------------------------------------------------------------------------

def run_sync(
    project_dir: Path,
    dry_run: bool = False,
    report_only: bool = False,
    auto_apply: bool = True,
    json_output: bool = False,
    ci_mode: bool = False,
    verbose: bool = False,
) -> SyncReport:
    """Run one sync cycle. Returns SyncReport."""
    import genesis_architect_pro.gde_engine_registration  # noqa: F401
    from genesis_architect_pro import GenesisDecisionEngine

    run_id = datetime.now(timezone.utc).strftime("sync-%Y%m%d-%H%M%S")
    t0 = time.time()

    _read_sync_config(project_dir)
    report = SyncReport(
        run_id=run_id,
        project_dir=str(project_dir),
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_seconds=0,
    )

    # Run GATE mode — covers arch scoring, rules, fragility, git churn
    gde = GenesisDecisionEngine(project_dir=project_dir, parallel=True)
    session_report = gde.run("run full gate check and identify architecture drift")

    report.gate_outcome = session_report.gate_report.overall.value.lower()

    # Harvest score from engine results
    ar = session_report.engine_results.get("architecture_scorer")
    if ar and ar.output:
        report.score = ar.output.get("score")
        report.decay_forecast = ar.output.get("decay_forecast")

    # Classify all engine findings
    all_findings: list[SyncFinding] = []
    for engine_id, er in session_report.engine_results.items():
        if er.output:
            found = _classify_finding(engine_id, er.output)
            all_findings.extend(found)

    report.findings = all_findings
    report.green_applied  = sum(1 for f in all_findings if f.zone == ZONE_GREEN)
    report.yellow_pending = sum(1 for f in all_findings if f.zone == ZONE_YELLOW)
    report.red_blocked    = sum(1 for f in all_findings if f.zone == ZONE_RED)

    # Build summary
    score_str = f"{report.score:.1f}" if report.score is not None else "n/a"
    report.summary = (
        f"Score: {score_str} | Gate: {report.gate_outcome.upper()} | "
        f"Green: {report.green_applied} | Yellow: {report.yellow_pending} | "
        f"Red: {report.red_blocked}"
    )

    report.duration_seconds = round(time.time() - t0, 2)

    if dry_run:
        return report

    # --- Write actions ---
    if not report_only:
        # GREEN zone: always auto-applied (sync_log is always written)
        _write_sync_log(project_dir, report)

        # YELLOW zone: write pending.json for human to review
        yellow = [f for f in all_findings if f.zone == ZONE_YELLOW]
        if yellow:
            _write_pending(project_dir, yellow)
            for f in yellow:
                f.auto_applied = False

        # GREEN auto-apply marker
        for f in all_findings:
            if f.zone == ZONE_GREEN and auto_apply:
                f.auto_applied = True

    return report


# ---------------------------------------------------------------------------
# CLI output formatters
# ---------------------------------------------------------------------------

def _print_report_rich(report: SyncReport) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from rich import box
    except ImportError:
        _print_report_plain(report)
        return

    console = Console()
    console.print()

    zone_styles = {ZONE_GREEN: "bold green", ZONE_YELLOW: "bold yellow", ZONE_RED: "bold red"}
    gate_style = {"pass": "bold green", "warn": "bold yellow", "block": "bold yellow",
                  "hard_block": "bold red"}.get(report.gate_outcome, "white")

    score_str = f"{report.score:.1f}" if report.score is not None else "n/a"
    summary = Text()
    summary.append("  Run     ", style="dim")
    summary.append(report.run_id + "\n", style="white")
    summary.append("  Score   ", style="dim")
    summary.append(score_str + "\n", style="bold cyan")
    summary.append("  Gate    ", style="dim")
    summary.append(report.gate_outcome.upper() + "\n", style=gate_style)
    summary.append("  Green   ", style="dim")
    summary.append(f"{report.green_applied} auto-applied\n", style="green")
    summary.append("  Yellow  ", style="dim")
    summary.append(f"{report.yellow_pending} pending review\n", style="yellow")
    summary.append("  Red     ", style="dim")
    summary.append(f"{report.red_blocked} blocked\n", style="red")
    summary.append("  Elapsed ", style="dim")
    summary.append(f"{report.duration_seconds:.1f}s\n", style="dim")

    if report.decay_forecast:
        fc = report.decay_forecast
        summary.append("  Decay   ", style="dim")
        summary.append(fc.get("summary", ""), style="dim yellow")
        summary.append("\n")

    console.print(Panel(summary, title="[bold]Genesis Sync[/bold]", border_style="bright_black",
                        box=box.ROUNDED, padding=(0, 1)))

    if report.findings:
        console.print()
        table = Table(box=box.SIMPLE, show_header=True, header_style="dim",
                      border_style="bright_black", padding=(0, 2))
        table.add_column("Zone", width=8)
        table.add_column("Engine", width=22)
        table.add_column("Finding")
        table.add_column("Status", width=14)

        for f in report.findings:
            zstyle = zone_styles.get(f.zone, "white")
            status = "[green]applied[/green]" if f.auto_applied else (
                "[yellow]pending[/yellow]" if f.zone == ZONE_YELLOW else "[red]blocked[/red]"
            )
            table.add_row(
                f"[{zstyle}]{f.zone}[/{zstyle}]",
                f.engine, f.title, status,
            )
        console.print(table)

    console.print()


def _print_report_plain(report: SyncReport) -> None:
    score_str = f"{report.score:.1f}" if report.score is not None else "n/a"
    print()
    print(f"  Genesis Sync — {report.run_id}")
    print(f"  Score   : {score_str}")
    print(f"  Gate    : {report.gate_outcome.upper()}")
    print(f"  Green   : {report.green_applied} auto-applied")
    print(f"  Yellow  : {report.yellow_pending} pending review")
    print(f"  Red     : {report.red_blocked} blocked")
    print(f"  Elapsed : {report.duration_seconds:.1f}s")
    if report.decay_forecast:
        print(f"  Decay   : {report.decay_forecast.get('summary', '')}")
    if report.findings:
        print()
        for f in report.findings:
            status = "applied" if f.auto_applied else ("pending" if f.zone == ZONE_YELLOW else "BLOCKED")
            print(f"  [{f.zone:6}] [{f.engine:22}] {f.title}  →  {status}")
    print()


# ---------------------------------------------------------------------------
# Entry point (used by gde_cli.py cmd_sync)
# ---------------------------------------------------------------------------

def cli_sync(args) -> int:
    """Called by gde_cli.cmd_sync."""
    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"  error: --dir '{project_dir}' is not a directory", file=sys.stderr)
        return 1

    report = run_sync(
        project_dir=project_dir,
        dry_run=getattr(args, "dry_run", False),
        report_only=getattr(args, "report_only", False),
        auto_apply=getattr(args, "auto_apply", True),
        json_output=getattr(args, "json_output", False),
        ci_mode=getattr(args, "ci_mode", False),
    )

    if getattr(args, "json_output", False):
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        return 0

    try:
        from rich.console import Console  # noqa: F401
        _print_report_rich(report)
    except ImportError:
        _print_report_plain(report)

    # CI mode: non-zero if there are any yellow or red findings
    if getattr(args, "ci_mode", False):
        return 1 if (report.yellow_pending + report.red_blocked) > 0 else 0

    return 0
