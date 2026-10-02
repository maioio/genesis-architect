#!/usr/bin/env python3
"""
prompt_export.py - Genesis Architect PRO

Turns approved refactoring-plan steps into self-contained prompts that can be
pasted into any LLM or saved for offline use. Nothing is sent anywhere and no
project file is edited. Generating the plan or reading the import graph may
refresh the analysis cache under .genesis/ (import_graph.json), as the other
Genesis analyses do; with --plan and --no-graph nothing is written except the
prompt files that --out-dir --apply asks for.

The approval gate
-----------------
Only steps named explicitly are exported: by id, by fingerprint, or "all" on
its own. Without a selection the CLI lists the steps and stops. A fingerprint
hashes a step's rule, title and operations, so it keeps naming the same step
when a regenerated plan renumbers the ids. A selection that matches no step,
or matches more than one, is an error, never a silent skip or a guess.

A plan read from a file is type-checked field by field (no coercion), its
step ids must be unique, and its tier counts and total impact are recomputed.

What goes into each prompt
--------------------------
  core-target        files the step modifies or moves (always in full)
  important-context  files the step deletes (abbreviated if the budget is tight)
  consumer-ref       modules that import a core target, from the import graph
                     (at most MAX_CONSUMERS, abbreviated)

Files to be created are described, not loaded. Placeholder paths such as
"[composition root]" are skipped. A path that is absolute, drive-relative or
resolves outside the project root (a symlink included) is refused, so a
hand-edited plan cannot pull outside files into a prompt.

Packing goes through prompt_budget against what the header, the trim notes and
the joins leave of the budget, so whenever that remainder is positive and the
files fit it, the whole prompt fits. The prompt names every file that was
abbreviated or dropped. over_budget is measured on the final prompt text, not
taken from the packer: it is set exactly when the prompt would still exceed the
budget with every file except the core targets dropped.

Prompts are UTF-8. When the console cannot encode one, the CLI stops with
exit 2 and points to --json (ASCII-escaped) or --out-dir (UTF-8 files).

Public API
----------
  step_fingerprint(step) -> str
  select_steps(plan, selection) -> list[RefactorStep]
  plan_from_dict(data) -> RefactoringPlan
  export_prompts(plan, root, selection, model=None, max_tokens=None, modules=None) -> PromptExport
  write_prompts(export, out_dir, apply=False) -> list[WriteAction]

Usage:
  python -m genesis_architect_pro.prompt_export [PATH]                  # list the steps
  python -m genesis_architect_pro.prompt_export [PATH] --steps 1,3
  python -m genesis_architect_pro.prompt_export [PATH] --steps all --plan plan.json --json
  python -m genesis_architect_pro.prompt_export [PATH] --steps 2 --out-dir prompts [--apply]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, NoReturn

from genesis_architect_pro.prompt_budget import (
    ABBREVIATED,
    CONSUMER_REF,
    DROPPED,
    FULL,
    IMPORTANT_CONTEXT,
    BudgetReport,
    collect_files,
    estimate_tokens,
    pack_prompt,
    resolve_budget,
)
from genesis_architect_pro.refactoring_planner import (
    RefactoringPlan,
    RefactorOperation,
    RefactorStep,
    _graph_modules,
    generate_plan,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL = "all"
FINGERPRINT_LENGTH = 8
MAX_CONSUMERS = 8

_CREATE = "CREATE"
_CONTEXT_OPS = frozenset({"DELETE"})   # every other non-CREATE type is a core target

CONSTRAINTS = (
    "Change only the files named under Operations.",
    "Keep behaviour unchanged: names that other modules import from a changed file must keep working.",
    "Return a unified diff for each modified file and the full content of each created file.",
    "If an operation cannot be done safely with the files below, name it and say what is "
    "missing instead of guessing.",
)

WOULD_WRITE = "would-write"
WRITTEN = "written"
EXISTS = "exists"

_TRIM_NOTE = "Context was trimmed to fit the budget. Do not assume the omitted parts:"
_NO_FILES = "(no existing files to show)"
_SLUG = re.compile(r"[^a-z0-9]+")
_MAX_SLUG = 40   # a rule read from --plan can be any length; filenames cannot
_MISSING = object()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class StepPrompt:
    """
    One exported prompt.

    budget:        the file packing, done against what the prompt text leaves
    budget_tokens: the budget for the whole prompt
    """
    step: RefactorStep
    fingerprint: str
    prompt: str
    budget: BudgetReport
    budget_tokens: int
    warnings: list[str] = field(default_factory=list)

    @property
    def used_tokens(self) -> int:
        return estimate_tokens(self.prompt)

    @property
    def over_budget(self) -> bool:
        # Derived from the final text on every read, never stored.
        return self.used_tokens > self.budget_tokens

    def to_dict(self, include_prompt: bool = True) -> dict:
        data = {
            "step_id": self.step.id,
            "fingerprint": self.fingerprint,
            "rule": self.step.rule,
            "title": self.step.title,
            "budget_tokens": self.budget_tokens,
            "used_tokens": self.used_tokens,
            "over_budget": self.over_budget,
            "files": self.budget.to_dict()["files"],
            "warnings": list(self.warnings),
        }
        if include_prompt:
            data["prompt"] = self.prompt
        return data


@dataclass
class PromptExport:
    model: str | None
    budget_tokens: int
    prompts: list[StepPrompt] = field(default_factory=list)

    @property
    def over_budget(self) -> bool:
        return any(p.over_budget for p in self.prompts)

    def render(self) -> str:
        return "\n\n".join(p.prompt for p in self.prompts)

    def to_dict(self, include_prompts: bool = True) -> dict:
        return {
            "model": self.model,
            "budget_tokens": self.budget_tokens,
            "over_budget": self.over_budget,
            "prompts": [p.to_dict(include_prompts) for p in self.prompts],
        }


@dataclass
class WriteAction:
    path: str      # file name inside out_dir
    status: str    # would-write | written | exists


# ---------------------------------------------------------------------------
# Plan handling and the approval gate
# ---------------------------------------------------------------------------

def step_fingerprint(step: RefactorStep) -> str:
    """A short hash of what the step does, independent of its id."""
    payload = json.dumps(
        [step.rule, step.title, [[op.type, op.path, op.description] for op in step.operations]],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:FINGERPRINT_LENGTH]


def select_steps(plan: RefactoringPlan, selection: str | Iterable | None) -> list[RefactorStep]:
    """
    Return the steps named by *selection*, in plan order.

    selection is "all" on its own, a comma-separated string, or an iterable of
    step ids and fingerprints. Raises ValueError for an empty selection, a
    token that matches no step, a token that matches several steps (a shared
    id or fingerprint), or "all" mixed with other tokens.
    """
    if selection is None:
        tokens = []
    elif isinstance(selection, str):
        tokens = [t.strip() for t in selection.split(",") if t.strip()]
    else:
        tokens = [str(t).strip() for t in selection if str(t).strip()]
    if not tokens:
        raise ValueError("No steps selected: name step ids or fingerprints, or 'all'.")
    if any(t.lower() == ALL for t in tokens):
        if len(tokens) > 1:
            raise ValueError("'all' selects every step; it cannot be combined with other steps.")
        return list(plan.steps)

    by_fingerprint: dict[str, list[int]] = {}
    by_id: dict[int, list[int]] = {}
    for index, step in enumerate(plan.steps):
        by_fingerprint.setdefault(step_fingerprint(step), []).append(index)
        by_id.setdefault(step.id, []).append(index)

    chosen: set[int] = set()
    unknown, ambiguous = [], []
    for token in tokens:
        matches = by_fingerprint.get(token.lower())
        if matches is None and token.isascii() and token.isdigit():
            matches = by_id.get(int(token))
        if not matches:
            unknown.append(token)
        elif len(matches) > 1:
            ambiguous.append(token)
        else:
            chosen.add(matches[0])
    if unknown:
        available = ", ".join(str(s.id) for s in plan.steps) or "none: the plan has no steps"
        raise ValueError(f"No step matches {', '.join(unknown)} (step ids: {available}).")
    if ambiguous:
        raise ValueError(
            f"{', '.join(ambiguous)} matches more than one step: select by fingerprint "
            "when an id is shared, or by id when a fingerprint is shared."
        )
    return [plan.steps[i] for i in sorted(chosen)]


def _field(raw: dict, key: str, kinds: type | tuple[type, ...], default: Any = _MISSING) -> Any:
    """raw[key] if it has one of *kinds* (never bool), else *default* or ValueError."""
    if key not in raw:
        if default is _MISSING:
            raise ValueError(f"missing {key!r}")
        return default
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, kinds):
        names = " or ".join(k.__name__ for k in (kinds if isinstance(kinds, tuple) else (kinds,)))
        raise ValueError(f"{key!r} must be {names}, got {type(value).__name__}")
    return value


def _operation_from_dict(raw) -> RefactorOperation:
    if not isinstance(raw, dict):
        raise ValueError(f"an operation must be an object, got {type(raw).__name__}")
    return RefactorOperation(
        type=_field(raw, "type", str),
        path=_field(raw, "path", str),
        description=_field(raw, "description", str, ""),
    )


def _step_from_dict(raw) -> RefactorStep:
    if not isinstance(raw, dict):
        raise ValueError(f"a step must be an object, got {type(raw).__name__}")
    return RefactorStep(
        id=_field(raw, "id", int),
        tier=_field(raw, "tier", int),
        rule=_field(raw, "rule", str),
        priority=_field(raw, "priority", str),
        title=_field(raw, "title", str),
        why=_field(raw, "why", str, ""),
        operations=[_operation_from_dict(op) for op in _field(raw, "operations", list, [])],
        complexity=_field(raw, "complexity", str, "MEDIUM"),
        score_impact=_field(raw, "score_impact", int, 0),
        confidence=float(_field(raw, "confidence", (int, float), 0.8)),
        confidence_basis=_field(raw, "confidence_basis", str, ""),
    )


def plan_from_dict(data: dict) -> RefactoringPlan:
    """
    Rebuild a RefactoringPlan from RefactoringPlan.to_dict() output.

    Every field is type-checked rather than coerced, step ids must be unique,
    and tier counts and the total impact are recomputed from the steps rather
    than trusted from the file. Raises ValueError naming the first bad step.
    """
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise ValueError("Not a refactoring plan: expected an object with a 'steps' list.")
    steps = []
    for n, raw in enumerate(data["steps"], 1):
        try:
            steps.append(_step_from_dict(raw))
        except ValueError as exc:
            raise ValueError(f"Step {n} of the plan is malformed: {exc}") from exc
    duplicated = sorted(i for i, n in Counter(s.id for s in steps).items() if n > 1)
    if duplicated:
        raise ValueError(f"Step ids must be unique; repeated: {', '.join(map(str, duplicated))}")
    generated_at = data.get("generated_at")
    return RefactoringPlan(
        steps=steps,
        tier1_count=sum(1 for s in steps if s.tier == 1),
        tier2_count=sum(1 for s in steps if s.tier == 2),
        total_score_impact=sum(s.score_impact for s in steps),
        generated_at=generated_at if isinstance(generated_at, str) else "",
    )


# ---------------------------------------------------------------------------
# Choosing the files for a step
# ---------------------------------------------------------------------------

def _is_placeholder(path: str) -> bool:
    return path.startswith("[") and path.endswith("]")


def _safe_rel(root: Path, rel: str) -> str | None:
    """
    The path normalised to posix form relative to *root*, or None when it is
    empty, absolute, drive-relative, holds a NUL, or resolves outside *root*
    (symlinks included). The name stays lexical; resolve() only checks where
    it lands.
    """
    if not rel or "\x00" in rel or PureWindowsPath(rel).drive:
        return None
    norm = posixpath.normpath(rel.replace("\\", "/"))
    if norm in (".", "..") or norm.startswith(("../", "/")):
        return None
    try:
        base = root.resolve()
        (base / norm).resolve().relative_to(base)
    except (OSError, ValueError, RuntimeError):
        return None
    return norm


def _consumers(root: Path, targets: list[str], modules: dict | None,
               exclude: set[str], warnings: list[str]) -> list[str]:
    if not modules:
        return []
    by_path = {k.replace("\\", "/"): v for k, v in modules.items() if isinstance(k, str)}
    found: set[str] = set()
    for target in targets:
        entry = by_path.get(target)
        importers = entry.get("imported_by") if isinstance(entry, dict) else None
        if not isinstance(importers, (list, tuple)):
            continue
        for importer in importers:
            rel = _safe_rel(root, importer) if isinstance(importer, str) else None
            if rel is not None:
                found.add(rel)
    ordered = sorted(found - exclude)
    if len(ordered) > MAX_CONSUMERS:
        warnings.append(
            f"{len(ordered)} modules import the targets; the first {MAX_CONSUMERS} "
            "by path are included as references."
        )
        ordered = ordered[:MAX_CONSUMERS]
    return ordered


def _step_files(step: RefactorStep, root: Path,
                modules: dict | None) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (targets, context, consumers, warnings) for one step."""
    targets: list[str] = []
    context: list[str] = []
    warnings: list[str] = []
    for op in step.operations:
        if _is_placeholder(op.path):
            continue
        rel = _safe_rel(root, op.path)
        if rel is None:
            warnings.append(f"Refused {op.path!r}: not a path inside the project root.")
            continue
        op_type = op.type.upper()
        if op_type == _CREATE:
            if (root / rel).exists():
                warnings.append(f"{rel} is marked CREATE but already exists; "
                                "it is included so it is not overwritten blind.")
                targets.append(rel)
            continue
        (context if op_type in _CONTEXT_OPS else targets).append(rel)
    targets = list(dict.fromkeys(targets))
    context = [p for p in dict.fromkeys(context) if p not in targets]
    consumers = _consumers(root, targets, modules, set(targets) | set(context), warnings)
    return targets, context, consumers, warnings


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_header(step: RefactorStep, fingerprint: str, generated_at: str) -> str:
    provenance = f"fingerprint {fingerprint}" + (f" | plan {generated_at}" if generated_at else "")
    estimate = f"Planner estimate: +{step.score_impact} pts, confidence {step.confidence:.2f}"
    if step.confidence_basis:
        estimate += f" ({step.confidence_basis})"
    lines = [
        f"# Refactoring step {step.id}: {step.title}",
        f"<!-- Genesis Architect PRO prompt_export | {provenance} -->",
        "",
        "## Task",
        "",
        f"Rule: {step.rule} | Priority: {step.priority} | Tier: {step.tier} | "
        f"Complexity: {step.complexity}",
        estimate,
        "",
        "## Why",
        "",
        step.why or "(the plan records no rationale for this step)",
        "",
        "## Operations",
        "",
    ]
    for n, op in enumerate(step.operations, 1):
        lines.append(f"{n}. {op.type} `{op.path}`: {op.description}")
    if not step.operations:
        lines.append("(the plan lists no operations for this step)")
    lines += ["", "## Constraints", ""]
    lines += [f"- {c}" for c in CONSTRAINTS]
    lines.append("")
    return "\n".join(lines)


def _trim_notes(trimmed: list[tuple[str, str, str]]) -> str:
    if not trimmed:
        return ""
    lines = [_TRIM_NOTE] + [f"- {path} ({role}, {status})" for path, role, status in trimmed]
    return "\n".join(lines) + "\n\n"


def _render_files(report: BudgetReport) -> str:
    trimmed = [(f.path, f.role, f.status) for f in report.files if f.status != FULL]
    body = report.render() or _NO_FILES
    return "## Files\n\n" + _trim_notes(trimmed) + body


def _files_budget(budget: int, header: str, trimmable: list[tuple[str, str]],
                  n_files: int) -> int:
    """
    Tokens left for the file sections once the header, the worst-case trim
    notes (every trimmable file listed as abbreviated) and the joins between
    sections are reserved. When the packing fits this and the result is not
    clamped to 1, the final prompt fits *budget*: token estimates are
    subadditive, so the parts' sum bounds the whole.
    """
    worst = _trim_notes([(path, role, ABBREVIATED) for path, role in trimmable])
    joins = max(estimate_tokens(_NO_FILES), estimate_tokens("\n" * max(n_files - 1, 0)))
    fixed = estimate_tokens(header + "\n## Files\n\n" + worst + "\n") + joins
    return max(1, budget - fixed)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_prompts(plan: RefactoringPlan, root: str | Path, selection: str | Iterable,
                   model: str | None = None, max_tokens: int | None = None,
                   modules: dict | None = None) -> PromptExport:
    """
    Build one prompt per selected step.

    modules is the import graph's module map (for consumer references); pass
    None to leave consumers out. Raises NotADirectoryError for a bad root and
    ValueError for a bad selection or budget.
    """
    base = Path(root)
    if not base.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    label, budget = resolve_budget(model, max_tokens)
    steps = select_steps(plan, selection)
    export = PromptExport(model=label, budget_tokens=budget)

    for step in steps:
        fingerprint = step_fingerprint(step)
        targets, context, consumers, warnings = _step_files(step, base, modules)
        files, load_warnings = collect_files(base, targets, context, consumers)
        warnings += load_warnings

        header = _render_header(step, fingerprint, plan.generated_at)
        trimmable = ([(p, IMPORTANT_CONTEXT) for p in context]
                     + [(p, CONSUMER_REF) for p in consumers])
        report = pack_prompt(files, model=label,
                             max_tokens=_files_budget(budget, header, trimmable, len(files)))
        prompt = header + "\n" + _render_files(report) + "\n"
        step_prompt = StepPrompt(step, fingerprint, prompt, report, budget, warnings)

        dropped = report.by_status(DROPPED)
        if dropped:
            step_prompt.warnings.append(
                f"{len(dropped)} file(s) dropped to fit the budget: "
                + ", ".join(f.path for f in dropped)
            )
        if step_prompt.over_budget:
            used = step_prompt.used_tokens
            step_prompt.warnings.append(
                f"The prompt needs ~{used} tokens but the budget is {budget} "
                f"(over by ~{used - budget}): split the step or raise the budget."
            )
        export.prompts.append(step_prompt)
    return export


def prompt_filename(step_prompt: StepPrompt) -> str:
    slug = _SLUG.sub("-", step_prompt.step.rule.lower()).strip("-")[:_MAX_SLUG].strip("-") or "step"
    return f"step-{step_prompt.step.id:02d}-{slug}-{step_prompt.fingerprint}.md"


def write_prompts(export: PromptExport, out_dir: str | Path,
                  apply: bool = False) -> list[WriteAction]:
    """
    Write one Markdown file per prompt into *out_dir*.

    Dry-run unless apply is True. An existing file is never overwritten, even
    when it appears between the check and the write.
    """
    out = Path(out_dir)
    if out.exists() and not out.is_dir():
        raise NotADirectoryError(f"Not a directory: {out_dir}")
    actions = []
    for step_prompt in export.prompts:
        name = prompt_filename(step_prompt)
        target = out / name
        if target.exists():
            actions.append(WriteAction(name, EXISTS))
            continue
        if not apply:
            actions.append(WriteAction(name, WOULD_WRITE))
            continue
        out.mkdir(parents=True, exist_ok=True)
        try:
            with open(target, "x", encoding="utf-8", newline="\n") as fh:
                fh.write(step_prompt.prompt)
        except FileExistsError:
            actions.append(WriteAction(name, EXISTS))
            continue
        actions.append(WriteAction(name, WRITTEN))
    return actions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def format_step_list(plan: RefactoringPlan) -> str:
    if not plan.steps:
        return "The plan has no steps; nothing to export."
    lines = [
        f"Refactoring plan: {len(plan.steps)} step(s), +{plan.total_score_impact} pts estimated",
        f"  {'id':>3}  {'fingerprint':<11}  tier  {'priority':<8}  title",
    ]
    for s in plan.steps:
        lines.append(f"  {s.id:>3}  {step_fingerprint(s):<11}  {s.tier:>4}  {s.priority:<8}  {s.title}")
    lines.append("Nothing exported. Select steps with --steps <ids or fingerprints>, "
                 "comma-separated, or --steps all.")
    return "\n".join(lines)


def _load_plan(path: str) -> RefactoringPlan:
    return plan_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _fail(message: str) -> NoReturn:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(2)


def _emit(text: str) -> None:
    """Print *text*, or exit 2 with advice when the console cannot encode it."""
    try:
        print(text)
    except UnicodeEncodeError:
        _fail(f"the output has characters the console encoding ({sys.stdout.encoding}) "
              "cannot represent; use --json, or --out-dir to write UTF-8 files.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Offline Refactoring Prompt Export"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--plan", default=None,
                        help="plan JSON from refactoring_planner --json (default: generate one now)")
    parser.add_argument("--steps", default=None,
                        help="step ids or fingerprints, comma-separated, or 'all'; "
                             "without it the steps are listed and nothing is exported")
    parser.add_argument("--language", default=None)
    parser.add_argument("--model", default=None, help="budget preset (see prompt_budget)")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="explicit budget per prompt; overrides --model")
    parser.add_argument("--no-graph", action="store_true",
                        help="skip the import graph, so no consumer references")
    parser.add_argument("--out-dir", default=None,
                        help="write one .md per step here (dry-run unless --apply; never overwrites)")
    parser.add_argument("--apply", action="store_true", help="with --out-dir: write the files")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.apply and not args.out_dir:
        _fail("--apply only takes effect with --out-dir.")
    root = Path(args.project_path)
    if not root.is_dir():
        _fail(f"Not a directory: {args.project_path}")

    try:
        if args.plan:
            plan = _load_plan(args.plan)
        else:
            plan = generate_plan(root, language=args.language)
    except (OSError, ValueError) as exc:
        _fail(f"Could not load the plan: {exc}")

    if args.steps is None:
        _emit(format_step_list(plan))
        return

    modules = None if args.no_graph else _graph_modules(root.resolve(), args.language)

    try:
        export = export_prompts(plan, root, args.steps, model=args.model,
                                max_tokens=args.max_tokens, modules=modules)
    except ValueError as exc:
        _fail(str(exc))

    if args.out_dir:
        try:
            actions = write_prompts(export, args.out_dir, apply=args.apply)
        except OSError as exc:
            _fail(f"Could not write to {args.out_dir}: {exc}")
        if args.json:
            print(json.dumps({"apply": args.apply,
                              "actions": [a.__dict__ for a in actions]}, indent=2))
        else:
            for action in actions:
                print(f"  {action.status:<12} {action.path}")
            if not args.apply:
                print("Dry run: nothing written. Re-run with --apply to write.")
    elif args.json:
        print(json.dumps(export.to_dict(), indent=2))
    else:
        _emit(export.render())

    for step_prompt in export.prompts:
        for warning in step_prompt.warnings:
            print(f"WARNING: step {step_prompt.step.id}: {warning}", file=sys.stderr)
    if export.over_budget:
        sys.exit(1)


if __name__ == "__main__":
    main()
