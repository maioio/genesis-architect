"""Research Outline — the items x fields grid that precedes investigation.

Genesis's research_orchestrator is opportunistic: it gathers, then ranks
whatever it happened to find. There is no outline phase, so nothing defines
what *should* have been found before the search starts — which is why
coverage today can only be estimated after the fact (check_floor's repo
count) rather than measured against a stated target.

An Outline states the target first: `items` are the things to investigate
(candidate libraries, competitors, sources — whatever the research is about),
`fields` are the criteria to fill in for each one (license, maintenance,
bundle size, CVE history — whatever the decision actually needs). Coverage
becomes "fields filled / fields defined per item" instead of a guess.

This module is pure data: one dataclass plus JSON read/write. It imports
nothing else from genesis_architect.pro, so it cannot participate in a
`requires`/`handoffs` cycle — the L0 layer other engines build on, not one
that leans on them back.

JSON, not YAML: the project ships no PyYAML and stays dependency-light (see
source_registry.py's docstring for the same rule applied to its own catalog).
Outline and fields are still stored as two files, matching the source
pattern's actual reason for the split — items are curated per research run,
while a field framework is often reused or extended across several.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

OUTLINE_FILENAME = "outline.json"
FIELDS_FILENAME = "fields.json"


@dataclass
class Outline:
    """The research target, stated before any investigation starts.

    `items` and `fields` together form a grid: for each item, every field is
    a value to find. Both default to empty so a caller can build the topic
    first and fill in items/fields incrementally (e.g. during a confirm step
    with the user) before ever calling save_outline().
    """

    topic: str
    items: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _research_dir(project_root: Path) -> Path:
    return project_root / ".genesis" / "research"


def _outline_path(project_root: Path) -> Path:
    return _research_dir(project_root) / OUTLINE_FILENAME


def _fields_path(project_root: Path) -> Path:
    return _research_dir(project_root) / FIELDS_FILENAME


def save_outline(outline: Outline, project_root: Path) -> None:
    """Write `outline` to `.genesis/research/outline.json` + `fields.json`.

    Two files because the two halves are conceptually distinct (see module
    docstring), even though both are written together here.
    """
    research_dir = _research_dir(project_root)
    research_dir.mkdir(parents=True, exist_ok=True)

    outline_data = {
        "topic": outline.topic,
        "items": outline.items,
        "created_at": outline.created_at,
    }
    _outline_path(project_root).write_text(
        json.dumps(outline_data, indent=2), encoding="utf-8"
    )

    fields_data = {"fields": outline.fields}
    _fields_path(project_root).write_text(
        json.dumps(fields_data, indent=2), encoding="utf-8"
    )


def load_outline(project_root: Path) -> Outline | None:
    """Read an Outline back, or None if absent, incomplete, or corrupt.

    Fail-safe by design: a caller checking "is there an outline yet?" should
    never have to handle an exception to find out.
    """
    outline_path = _outline_path(project_root)
    fields_path = _fields_path(project_root)
    if not outline_path.is_file() or not fields_path.is_file():
        return None

    try:
        outline_data = json.loads(outline_path.read_text(encoding="utf-8"))
        fields_data = json.loads(fields_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    if not isinstance(outline_data, dict) or not isinstance(fields_data, dict):
        return None

    topic = outline_data.get("topic")
    if not isinstance(topic, str) or not topic:
        return None

    items = outline_data.get("items", [])
    fields = fields_data.get("fields", [])
    if not isinstance(items, list) or not isinstance(fields, list):
        return None
    if not all(isinstance(i, str) for i in items):
        return None
    if not all(isinstance(f, str) for f in fields):
        return None

    created_at = outline_data.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        created_at = datetime.now(timezone.utc).isoformat()

    return Outline(topic=topic, items=items, fields=fields, created_at=created_at)