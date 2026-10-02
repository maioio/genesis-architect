# `.genesis/` File Reference

Genesis keeps everything it learns about a project in a `.genesis/` directory at
the project root. It is plain text — auditable, diffable, and additive.

| Path | Written by | Contents |
|------|-----------|----------|
| `state.json` | Cross-session memory | last phase + timestamp, repo/pitfall counts |
| `project_memory.md` | Memory | what the project is, current state |
| `decision_log.md` | Decision / Memory | every significant decision + journal entry |
| `research_history.md` | Research | what was researched, when, result |
| `architecture_decisions.md` | Memory | ADRs — the drift baseline |
| `known_risks.md` | Recovery | open risks, severity, status |
| `lessons_learned.md` | Learning | best research profile per task kind (digest) |
| `learning/outcomes.jsonl` | Learning | raw recorded outcomes (append-only) |
| `knowledge/graph.json` | Knowledge Graph | the connective graph (nodes + edges) |
| `knowledge/research_sources.yaml` | Research | source registry + overrides |
| `telemetry/config.json` | Product Intelligence | consent state + anon install id |
| `telemetry/events.jsonl` | Product Intelligence | anonymous events (only if opted in) |
| `evidence_packs/` | Research | one file per Evidence Pack |
| `reports/` | Validation / Recovery | generated reports |
| `rules.json` | you | `genesis gate` thresholds |
| `model.json` / `score_history.jsonl` | Architecture | model snapshot + score trend |

## Notes

- **Additive + versioned.** A bad `model.json` can be reverted from git history or
  the committed snapshot.
- **Safe to commit** — except `telemetry/` (anonymous, but local by default) and
  any planning area you keep private. Decision log + ADRs are *meant* to be
  committed.
- **Corrupt cache self-heals** — Genesis rebuilds derived files from source.
