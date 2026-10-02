#!/usr/bin/env python3
"""
prompt_budget.py - Genesis Architect PRO

Keeps an LLM prompt inside a model's context budget.

Files are packed by role, in priority order:
  core-target        - always included in full (the files a step changes)
  important-context  - in full while the budget allows, else abbreviated, else dropped
  consumer-ref       - abbreviated (first 20 lines + export lines + last 5 lines),
                       dropped when even that does not fit

Tokens are estimated as ceil(chars / 4) over the rendered section (header and
fence included), so the budget covers what is actually sent. This is a
heuristic, not a tokenizer: treat presets as a planning budget with headroom,
not as the model's hard window.

Overflow is never silent. When the core targets alone exceed the budget the
report sets over_budget and says by how much; every dropped file is named in
the warnings.

Public API
----------
  estimate_tokens(text) -> int
  abbreviate(content) -> str
  pack_prompt(files, model=None, max_tokens=None) -> BudgetReport
  collect_files(root, targets, context, consumers) -> (files, warnings)

Usage:
  python -m genesis_architect_pro.prompt_budget --target src/a.py --consumer src/b.py
  python -m genesis_architect_pro.prompt_budget --target src/a.py --model qwen-32b --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORE_TARGET = "core-target"
IMPORTANT_CONTEXT = "important-context"
CONSUMER_REF = "consumer-ref"
ROLES = (CORE_TARGET, IMPORTANT_CONTEXT, CONSUMER_REF)

FULL = "full"
ABBREVIATED = "abbreviated"
DROPPED = "dropped"

CHARS_PER_TOKEN = 4
HEAD_LINES = 20
TAIL_LINES = 5

# Planning budgets in tokens, not the models' advertised windows.
MODEL_PRESETS: dict[str, int] = {
    "claude": 60_000,
    "qwen-32b": 8_000,
}
DEFAULT_MODEL = "claude"

# Top-level lines that declare a module's public surface (Python and JS/TS).
_EXPORT_PREFIXES = (
    "def ", "async def ", "class ", "__all__",
    "export ", "module.exports", "exports.",
)
_BACKTICK_RUN = re.compile(r"`+")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PromptFile:
    """One file offered to the packer, with the role that sets its priority."""
    path: str
    content: str
    role: str = CONSUMER_REF


@dataclass
class PackedFile:
    """
    What the packer did with one file.

    tokens:          tokens the rendered section costs (0 when dropped)
    original_tokens: tokens of the raw file content, for comparison
    content:         the rendered section ("" when dropped)
    """
    path: str
    role: str
    status: str          # full | abbreviated | dropped
    tokens: int
    original_tokens: int
    content: str = ""


@dataclass
class BudgetReport:
    model: str | None
    budget_tokens: int
    used_tokens: int = 0
    files: list[PackedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    over_budget: bool = False

    def by_status(self, status: str) -> list[PackedFile]:
        return [f for f in self.files if f.status == status]

    @property
    def ok(self) -> bool:
        """True when everything offered fits, in full or abbreviated."""
        return not self.over_budget and not self.by_status(DROPPED)

    def render(self) -> str:
        """The prompt body: every included section, in packing order."""
        return "\n".join(f.content for f in self.files if f.status != DROPPED)

    def to_dict(self, include_content: bool = False) -> dict:
        files = []
        for f in self.files:
            entry = {
                "path": f.path,
                "role": f.role,
                "status": f.status,
                "tokens": f.tokens,
                "original_tokens": f.original_tokens,
            }
            if include_content:
                entry["content"] = f.content
            files.append(entry)
        return {
            "model": self.model,
            "budget_tokens": self.budget_tokens,
            "used_tokens": self.used_tokens,
            "over_budget": self.over_budget,
            "ok": self.ok,
            "counts": {s: len(self.by_status(s)) for s in (FULL, ABBREVIATED, DROPPED)},
            "files": files,
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Estimate tokens as ceil(chars / 4)."""
    return -(-len(text) // CHARS_PER_TOKEN)


def resolve_budget(model: str | None = None,
                   max_tokens: int | None = None) -> tuple[str | None, int]:
    """
    Return (model_label, budget_tokens).

    An explicit max_tokens wins over a preset. An unknown preset name raises
    instead of falling back, so a typo never packs against the wrong budget.
    """
    if max_tokens is not None:
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")
        return model, max_tokens
    name = (model or DEFAULT_MODEL).lower()
    if name not in MODEL_PRESETS:
        known = ", ".join(sorted(MODEL_PRESETS))
        raise ValueError(
            f"Unknown model preset {model!r} (known: {known}). "
            "Pass max_tokens to set a budget directly."
        )
    return name, MODEL_PRESETS[name]


def _is_export_line(line: str) -> bool:
    if not line or line[0] in " \t":
        return False
    return line.startswith(_EXPORT_PREFIXES)


def abbreviate(content: str, head: int = HEAD_LINES, tail: int = TAIL_LINES) -> str:
    """
    Keep the first *head* lines, top-level export lines, and the last *tail*
    lines. A file short enough to keep whole is returned unchanged.
    """
    lines = content.splitlines()
    if len(lines) <= head + tail:
        return content
    middle = lines[head:len(lines) - tail]
    exports = [ln for ln in middle if _is_export_line(ln)]
    omitted = len(middle) - len(exports)
    out = list(lines[:head])
    out.append(f"... [{omitted} lines omitted, {len(exports)} export line(s) kept] ...")
    if exports:
        out.extend(exports)
        out.append("...")
    out.extend(lines[-tail:])
    return "\n".join(out)


def _fence(body: str) -> str:
    """A backtick fence longer than any backtick run inside *body*."""
    longest = max((len(m.group(0)) for m in _BACKTICK_RUN.finditer(body)), default=0)
    return "`" * max(3, longest + 1)


def _section(path: str, role: str, status: str, body: str) -> str:
    fence = _fence(body)
    return f"### {path}  [{role}, {status}]\n{fence}\n{body}\n{fence}\n"


def _ordered_unique(files: list[PromptFile]) -> list[PromptFile]:
    """
    Sort by role priority (stable within a role) and keep each path once,
    under its highest-priority role.
    """
    for f in files:
        if f.role not in ROLES:
            raise ValueError(f"Unknown role {f.role!r} for {f.path} (known: {', '.join(ROLES)})")
    rank = {role: i for i, role in enumerate(ROLES)}
    seen: set[str] = set()
    out = []
    for f in sorted(files, key=lambda f: rank[f.role]):
        key = f.path.replace("\\", "/")
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


# ---------------------------------------------------------------------------
# Packing
# ---------------------------------------------------------------------------

def pack_prompt(files: list[PromptFile], model: str | None = None,
                max_tokens: int | None = None) -> BudgetReport:
    """Pack *files* into the budget for *model* (or an explicit *max_tokens*)."""
    label, budget = resolve_budget(model, max_tokens)
    report = BudgetReport(model=label, budget_tokens=budget)
    used = 0
    core_tokens = 0

    for f in _ordered_unique(files):
        original = estimate_tokens(f.content)
        full_section = _section(f.path, f.role, FULL, f.content)
        full_tokens = estimate_tokens(full_section)

        if f.role == CORE_TARGET:
            report.files.append(PackedFile(f.path, f.role, FULL, full_tokens, original, full_section))
            used += full_tokens
            core_tokens += full_tokens
            continue

        if f.role == IMPORTANT_CONTEXT and used + full_tokens <= budget:
            report.files.append(PackedFile(f.path, f.role, FULL, full_tokens, original, full_section))
            used += full_tokens
            continue

        short = abbreviate(f.content)
        if short == f.content:
            status, section, tokens = FULL, full_section, full_tokens
        else:
            status = ABBREVIATED
            section = _section(f.path, f.role, ABBREVIATED, short)
            tokens = estimate_tokens(section)

        if used + tokens <= budget:
            report.files.append(PackedFile(f.path, f.role, status, tokens, original, section))
            used += tokens
        else:
            report.files.append(PackedFile(f.path, f.role, DROPPED, 0, original))

    report.used_tokens = used
    budget_label = f"{label} budget" if label else "budget"
    if core_tokens > budget:
        report.over_budget = True
        report.warnings.append(
            f"Core targets alone need ~{core_tokens} tokens but the {budget_label} is "
            f"{budget} (over by ~{core_tokens - budget}). The prompt will overflow: "
            "split the step into smaller ones or use a larger budget."
        )
    dropped = report.by_status(DROPPED)
    if dropped:
        names = ", ".join(f.path for f in dropped)
        report.warnings.append(
            f"{len(dropped)} file(s) dropped to fit the {budget_label} of {budget}: {names}"
        )
    return report


# ---------------------------------------------------------------------------
# Disk loading
# ---------------------------------------------------------------------------

def collect_files(root: str | Path, targets: list[str] | None = None,
                  context: list[str] | None = None,
                  consumers: list[str] | None = None) -> tuple[list[PromptFile], list[str]]:
    """
    Read files relative to *root* into PromptFiles.

    Returns (files, warnings). A missing or unreadable file becomes a warning,
    never a silent omission.
    """
    base = Path(root)
    files: list[PromptFile] = []
    warnings: list[str] = []
    for role, paths in ((CORE_TARGET, targets), (IMPORTANT_CONTEXT, context),
                        (CONSUMER_REF, consumers)):
        for rel in paths or []:
            path = base / rel
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                warnings.append(f"Could not read {rel} ({role}): {exc.strerror or exc}")
                continue
            files.append(PromptFile(path=rel.replace("\\", "/"), content=content, role=role))
    return files, warnings


def print_budget_report(report: BudgetReport) -> None:
    label = report.model or "custom"
    print(f"\nPrompt Budget  ({label}: ~{report.used_tokens} / {report.budget_tokens} tokens)")
    for f in report.files:
        print(f"  {f.status:<12} {f.role:<18} {f.tokens:>7}  {f.path}")
    for w in report.warnings:
        print(f"  WARNING: {w}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Prompt Budget Manager"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--target", action="append", default=[],
                        help="core-target file (always in full); repeatable")
    parser.add_argument("--context", action="append", default=[],
                        help="important-context file; repeatable")
    parser.add_argument("--consumer", action="append", default=[],
                        help="consumer-ref file (abbreviated); repeatable")
    parser.add_argument("--model", default=None,
                        help=f"budget preset: {', '.join(sorted(MODEL_PRESETS))}")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="explicit budget; overrides --model")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--render", action="store_true",
                        help="print the packed prompt body instead of the report")
    args = parser.parse_args()

    files, load_warnings = collect_files(args.root, args.target, args.context, args.consumer)
    try:
        report = pack_prompt(files, model=args.model, max_tokens=args.max_tokens)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    report.warnings = load_warnings + report.warnings

    if args.render:
        print(report.render())
    elif args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_budget_report(report)

    if report.over_budget:
        sys.exit(1)


if __name__ == "__main__":
    main()
