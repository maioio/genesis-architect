"""Genesis State & Caching Engine.

A local, dependency-free (stdlib `sqlite3`) cache that lets a Genesis session
avoid two kinds of repeated, wasted work across a project's lifetime:

**Re-discovering what's already installed.** The ``tool_catalog`` table is a
durable record of the MCP servers, skills, and libraries a session has
already confirmed are present, so a later session doesn't have to re-probe
for them from scratch.

**Re-reading unchanged files.** The ``config_cache`` table pairs a file's
SHA-256 content hash with a compact JSON summary of what was learned from it.
:meth:`CacheEngine.validate` is the whole mechanism: hash the file (cheap,
local, deterministic - no LLM call, no I/O beyond the read itself), compare
against what's on record, and if they match, hand back the cached summary
instead of re-parsing or re-analysing the file. A hash mismatch, or no
record at all, is always a miss - the cache can only save work, never skip
work that hasn't actually been verified unchanged.

**What this deliberately does not do.** There is no auto-discovery scanner
and no auto-computed ``performance_rating``. Inventing a heuristic score with
nothing real behind it would be the same category of unfounded claim this
project works elsewhere to avoid - a rating is either supplied by whoever
actually measured something, or it stays ``NULL``. Auto-population (scanning
``~/.claude.json`` for MCP servers, skill directories, package manifests) is a
distinct, separate design problem with its own questions about staleness and
cost, and does not belong bundled into the storage engine.

Location: ``.genesis/cache.db`` under the project directory, matching the
existing ``.genesis/`` convention used by ``genesis_state.py`` and
``evidence_pack.py`` for machine-owned files. It is never authoritative for
anything a human edits by hand - deleting it costs re-work, never data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "CacheEngine",
    "CacheEngineError",
    "ToolEntry",
    "ValidationResult",
    "db_path",
    "hash_file",
    "main",
]

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_catalog (
    name                TEXT NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN ('mcp', 'skill', 'library')),
    scope               TEXT NOT NULL CHECK (scope IN ('global', 'local')),
    version             TEXT,
    performance_rating  REAL,
    notes               TEXT NOT NULL DEFAULT '',
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (name, scope)
);

CREATE TABLE IF NOT EXISTS config_cache (
    path            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    summary         TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    -- Keyed by (path, content_hash), not path alone: a file that oscillates
    -- between two known states (a branch switch, an undo) should still hit
    -- on whichever hash is currently on disk, not only the most recent one.
    PRIMARY KEY (path, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_config_cache_path ON config_cache(path);
"""

_VALID_KINDS = ("mcp", "skill", "library")
_VALID_SCOPES = ("global", "local")


class CacheEngineError(RuntimeError):
    """The cache could not be read or written where a miss is not the answer."""


def db_path(project_dir: str | Path = ".") -> Path:
    """``<project_dir>/.genesis/cache.db``."""
    return Path(project_dir) / ".genesis" / "cache.db"


def hash_file(path: str | Path, *, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes, streamed so a large file isn't loaded whole.

    Raises:
        FileNotFoundError: if ``path`` does not exist. Propagated rather than
            caught, because a caller asking to hash a file that isn't there
            has a bug worth seeing, not a cache miss worth swallowing.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ToolEntry:
    """One row of the tool catalog."""

    name: str
    kind: str                          # "mcp" | "skill" | "library"
    scope: str                         # "global" | "local"
    version: str | None
    performance_rating: float | None
    notes: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "scope": self.scope,
            "version": self.version, "performance_rating": self.performance_rating,
            "notes": self.notes, "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of checking one file against the cache.

    ``summary`` is populated only when ``hit`` is True. On a miss the caller
    is expected to do the real work, then call :meth:`CacheEngine.store` with
    ``content_hash`` (already computed here - no need to hash twice) and the
    freshly produced summary.
    """

    path: str
    content_hash: str
    hit: bool
    summary: dict[str, Any] | None = None


def _normalise(path: str | Path) -> str:
    """A stable lookup key: absolute, OS-native separators normalised to '/'.

    Without this, the same file looked up as ``./x.json`` from one working
    directory and an absolute path from another would be treated as two
    different files, and every lookup from a different cwd would be a false
    miss.
    """
    return Path(path).expanduser().resolve().as_posix()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class CacheEngine:
    """One project's cache: the tool catalog and the config/workspace cache.

    Holds one open SQLite connection for the engine's lifetime. Not shared
    across threads; a Genesis session is single-threaded, so that is not a
    real constraint. Use as a context manager to guarantee the connection is
    closed, or call :meth:`close` explicitly.
    """

    def __init__(self, project_dir: str | Path = "."):
        self.project_dir = Path(project_dir)
        self.path = db_path(self.project_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(str(self.path))
        except sqlite3.Error as exc:
            raise CacheEngineError(f"could not open {self.path}: {exc}") from exc
        self._conn.row_factory = sqlite3.Row
        # WAL: a crash mid-write leaves the previous state readable rather
        # than a corrupt file. Cheap insurance for something that lives on a
        # developer's own disk and may be interrupted by Ctrl-C at any time.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        self._conn.commit()

    def __enter__(self) -> CacheEngine:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _write(self) -> Generator[sqlite3.Connection]:
        """One transaction: commits on success, rolls back on any exception."""
        with self._conn:
            yield self._conn

    # -- tool catalog -------------------------------------------------------

    def register_tool(
        self, name: str, kind: str, scope: str, *,
        version: str | None = None,
        performance_rating: float | None = None,
        notes: str = "",
    ) -> ToolEntry:
        """Insert or update one tool's catalog row.

        ``(name, scope)`` is the identity: the same tool can be registered
        once as ``global`` (e.g. installed for every project) and separately
        as ``local`` (pinned to this one), and the two rows are independent.

        Raises:
            ValueError: for an invalid ``kind`` or ``scope``, caught here
                rather than left to surface as an opaque SQLite CHECK
                violation.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("tool name must not be empty")
        if kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {_VALID_KINDS}, got {kind!r}")
        if scope not in _VALID_SCOPES:
            raise ValueError(f"scope must be one of {_VALID_SCOPES}, got {scope!r}")
        if performance_rating is not None and not (0.0 <= performance_rating <= 5.0):
            raise ValueError(
                f"performance_rating must be between 0.0 and 5.0, got "
                f"{performance_rating}"
            )

        updated_at = _now()
        with self._write() as conn:
            conn.execute(
                """
                INSERT INTO tool_catalog
                    (name, kind, scope, version, performance_rating, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, scope) DO UPDATE SET
                    kind = excluded.kind,
                    version = excluded.version,
                    performance_rating = excluded.performance_rating,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (name, kind, scope, version, performance_rating, notes, updated_at),
            )
        return ToolEntry(name, kind, scope, version, performance_rating, notes, updated_at)

    def get_tool(self, name: str, scope: str) -> ToolEntry | None:
        row = self._conn.execute(
            "SELECT * FROM tool_catalog WHERE name = ? AND scope = ?", (name, scope)
        ).fetchone()
        return _row_to_tool(row) if row else None

    def list_tools(self, *, kind: str | None = None,
                   scope: str | None = None) -> list[ToolEntry]:
        """All catalog entries, optionally filtered. Sorted by name for
        stable, diffable output."""
        clauses, params = [], []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if scope is not None:
            clauses.append("scope = ?")
            params.append(scope)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        # noqa: S608 below is safe - clauses come only from the fixed internal
        # set above ("kind = ?", "scope = ?"), never user text; every actual
        # value is a bound placeholder, not interpolated.
        query = f"SELECT * FROM tool_catalog {where} ORDER BY name, scope"  # noqa: S608
        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_tool(r) for r in rows]

    def remove_tool(self, name: str, scope: str) -> bool:
        """True if a row was actually removed."""
        with self._write() as conn:
            cur = conn.execute(
                "DELETE FROM tool_catalog WHERE name = ? AND scope = ?", (name, scope)
            )
        return cur.rowcount > 0

    # -- config / workspace file cache --------------------------------------

    def validate(self, file_path: str | Path) -> ValidationResult:
        """Hash ``file_path`` and check it against the cache.

        Always computes the hash - that part is cheap and is what makes the
        comparison trustworthy. What the caller skips on a hit is everything
        *after* the hash: re-reading the file's content, re-parsing it,
        re-summarising it. That's where the token budget actually goes.

        Looked up by ``(path, content_hash)`` together, not by path alone: a
        file that oscillates between known states - a branch switch, an
        undo - still hits on whichever hash is currently on disk, because
        that exact content was genuinely seen before. Only a hash this path
        has never produced is a real miss.
        """
        key = _normalise(file_path)
        current_hash = hash_file(file_path)
        row = self._conn.execute(
            "SELECT summary FROM config_cache WHERE path = ? AND content_hash = ?",
            (key, current_hash),
        ).fetchone()

        if row is not None:
            try:
                summary = json.loads(row["summary"])
            except json.JSONDecodeError as exc:
                # A hand-edited or corrupted cache row is a miss, not a crash:
                # the caller does the real work and store() repairs the row.
                raise CacheEngineError(
                    f"cached summary for {key} is not valid JSON ({exc}); "
                    "treat as a miss and re-store it"
                ) from exc
            return ValidationResult(path=key, content_hash=current_hash,
                                    hit=True, summary=summary)

        return ValidationResult(path=key, content_hash=current_hash, hit=False)

    def store(self, file_path: str | Path, content_hash: str,
             summary: dict[str, Any]) -> None:
        """Persist a freshly computed summary, keyed by the file's hash.

        ``content_hash`` is a parameter rather than recomputed here because
        :meth:`validate` already paid that cost once; hashing the same file
        twice per validate-then-store cycle would be pure waste.
        """
        key = _normalise(file_path)
        with self._write() as conn:
            conn.execute(
                """
                INSERT INTO config_cache (path, content_hash, summary, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(path, content_hash) DO UPDATE SET
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
                """,
                (key, content_hash, json.dumps(summary, ensure_ascii=False), _now()),
            )

    def invalidate(self, file_path: str | Path) -> bool:
        """Drop every cached version of this path. True if any existed.

        Deliberately all versions, not just the current hash: "forget this
        file" should not leave an old, unrelated hash sitting in the table
        ready to produce a hit if the file is ever reverted to it later.
        """
        key = _normalise(file_path)
        with self._write() as conn:
            cur = conn.execute("DELETE FROM config_cache WHERE path = ?", (key,))
        return cur.rowcount > 0

    # -- introspection --------------------------------------------------

    def stats(self) -> dict[str, Any]:
        tools = self._conn.execute("SELECT COUNT(*) FROM tool_catalog").fetchone()[0]
        # Distinct paths, not row count: one path can have several cached
        # hash-versions, and "files cached" should answer "how many files
        # does this know about," not "how many snapshots exist."
        files = self._conn.execute(
            "SELECT COUNT(DISTINCT path) FROM config_cache"
        ).fetchone()[0]
        return {
            "db_path": str(self.path),
            "tools_catalogued": tools,
            "files_cached": files,
            "schema_version": _SCHEMA_VERSION,
        }


def _row_to_tool(row: sqlite3.Row) -> ToolEntry:
    return ToolEntry(
        name=row["name"], kind=row["kind"], scope=row["scope"],
        version=row["version"], performance_rating=row["performance_rating"],
        notes=row["notes"], updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# CLI - matches the argparse subcommand convention of genesis_state.py, so
# scripts/cache_engine.py (a thin delegating shim, per that file's pattern)
# is what a Genesis session actually invokes.
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis State & Caching Engine")
    sub = parser.add_subparsers(dest="command", required=True)

    rt = sub.add_parser("register-tool")
    rt.add_argument("project_dir")
    rt.add_argument("name")
    rt.add_argument("--kind", required=True, choices=_VALID_KINDS)
    rt.add_argument("--scope", required=True, choices=_VALID_SCOPES)
    rt.add_argument("--version")
    rt.add_argument("--performance-rating", type=float)
    rt.add_argument("--notes", default="")

    lt = sub.add_parser("list-tools")
    lt.add_argument("project_dir")
    lt.add_argument("--kind", choices=_VALID_KINDS)
    lt.add_argument("--scope", choices=_VALID_SCOPES)

    xt = sub.add_parser("remove-tool")
    xt.add_argument("project_dir")
    xt.add_argument("name")
    xt.add_argument("--scope", required=True, choices=_VALID_SCOPES)

    va = sub.add_parser(
        "validate",
        help="hash a file and check it against the cache; exit 0 on a hit "
             "(summary on stdout), exit 1 on a miss (hash on stdout, so the "
             "caller can pass it straight to store without hashing again)",
    )
    va.add_argument("project_dir")
    va.add_argument("file_path")

    st = sub.add_parser("store")
    st.add_argument("project_dir")
    st.add_argument("file_path")
    st.add_argument("--content-hash", required=True)
    st.add_argument("--summary", required=True, help="a JSON object, as a string")

    iv = sub.add_parser("invalidate")
    iv.add_argument("project_dir")
    iv.add_argument("file_path")

    sub.add_parser("stats").add_argument("project_dir")

    args = parser.parse_args()

    with CacheEngine(args.project_dir) as engine:
        if args.command == "register-tool":
            entry = engine.register_tool(
                args.name, args.kind, args.scope, version=args.version,
                performance_rating=args.performance_rating, notes=args.notes,
            )
            print(json.dumps(entry.to_dict()))
            return 0

        if args.command == "list-tools":
            entries = engine.list_tools(kind=args.kind, scope=args.scope)
            print(json.dumps([e.to_dict() for e in entries], indent=2))
            return 0

        if args.command == "remove-tool":
            removed = engine.remove_tool(args.name, args.scope)
            if not removed:
                print(f"no such tool: {args.name} ({args.scope})", file=sys.stderr)
                return 1
            print(json.dumps({"removed": True}))
            return 0

        if args.command == "validate":
            result = engine.validate(args.file_path)
            if result.hit:
                print(json.dumps(result.summary))
                return 0
            print(json.dumps({"hit": False, "content_hash": result.content_hash}))
            return 1

        if args.command == "store":
            try:
                summary = json.loads(args.summary)
            except json.JSONDecodeError as exc:
                print(f"--summary is not valid JSON: {exc}", file=sys.stderr)
                return 1
            engine.store(args.file_path, args.content_hash, summary)
            print(json.dumps({"stored": True}))
            return 0

        if args.command == "invalidate":
            found = engine.invalidate(args.file_path)
            print(json.dumps({"invalidated": found}))
            return 0

        if args.command == "stats":
            print(json.dumps(engine.stats(), indent=2))
            return 0

    return 1  # pragma: no cover - unreachable, argparse enforces `required=True`


if __name__ == "__main__":
    raise SystemExit(main())
