# Changelog / Versioning

Genesis follows semantic versioning. Pro and Free are versioned independently;
Pro depends on a compatible Free core.

## Updating

- **pip:** `pip install -U genesis-architect-pro` — the changelog is surfaced.
- **desktop (future):** the Tauri updater handles signed releases, opt-in, with
  rollback. Updates are never applied silently mid-task.

## Recent capabilities (Pro v6.x — "AI Engineering Partner")

**v6.4** completed the partner experience:

- **Memory Engine + Decision Journal** — per-project Markdown memory under
  `.genesis/` (project memory, decision log, research history, ADRs, known risks,
  lessons). See [Memory + Learning](24_memory_learning.md).
- **UI Engine** — Floating Assistant + Canvas Workspace as a zero-setup
  self-contained HTML view of the engine outputs.

**v6.3** added the research-truth layer:

- **Research Source Registry** — a ranked, configurable catalog of 25+ sources;
  new sources can be added per-project without changing the engine. See
  [Source Registry](13_source_registry.md).
- **Reddit Answers workflow** — Developer Field Intelligence with a binding
  verification rule. See [Field Intelligence](11_field_intelligence.md).
- **Evidence Packs** — honest, source-ranked proof behind every recommendation.
  See [Evidence Packs](12_evidence_packs.md).

The v2 evolution added the intelligence layer on top of the architecture engines:

- **Decision Engine** + engine adapters — orchestrates the real engines through
  the lifecycle, with dependency ordering and graceful degradation.
- **Knowledge Graph Engine** — cross-source connective intelligence
  (`.genesis/knowledge/graph.json`).
- **Learning Engine** — per-project research-strategy learning with honest
  confidence.
- **Product Intelligence** — anonymous, opt-in, default-off telemetry.
- **First-run readiness** — the no-setup customer doctor + offline reporting.
- **Knowledge-graph-backed recovery** — do-not-touch zones cross-referenced with
  live CVEs.

Earlier v6.0 added the 8 codebase-intelligence engines (import graph,
architecture scorer, anti-pattern detector, drift detection, dependency index,
recovery report, git intelligence, security templates).

## Stability

Every release runs the full test suite (1,300+ tests) plus the architecture gate
and security checks before publishing. No release ships with failing tests.
