# Threat model

A short, evidence-linked statement of what Genesis protects, from whom, and where the protection
is tested. It complements [SECURITY.md](../../SECURITY.md), which has the reporting policy and
scope. It is not a formal audit.

## Assets

- Files on the user's machine outside the directory Genesis was pointed at.
- Secrets that exist in a repository Genesis analyzes.
- The user's Python environment (what gets installed into it).

## Actors and inputs treated as untrusted

| Input | Why it is untrusted |
|---|---|
| The repository being analyzed (file names, source text, docs) | Anyone can publish a repository |
| Text mined from GitHub issues and other research sources | Written by third parties |
| URLs and hosts returned by research sources | Can be crafted to look like a trusted host |
| Paths supplied as arguments | Can contain `..` or point elsewhere |

## Threats and current mitigations

| Threat | Mitigation | Evidence |
|---|---|---|
| Write outside the target directory by path traversal | Resolved-path containment check before writing | `_safe_path` in `core/drift_detector.py` and `core/research_validator.py`; `tests/test_scaffold_generator.py`, `tests/test_mitigation_enforcer.py`, `tests/test_research_validator.py` |
| Code of an analyzed repository gets executed | Analysis parses source with `ast.parse` and does not import or run it | `core/import_graph.py`; `core/drift_detector.py` documents "no exec, no subprocess" |
| Secret copied into a report | Scanner output is redacted | `tests/test_secrets_scanner.py` |
| Spoofed source host accepted as trusted | Hosts are matched on the parsed hostname | `tests/test_urls.py` |
| Unwanted package installation | Auto-install is only in the voice setup path and is disabled by `GENESIS_NO_AUTO_INSTALL=1` | `pro/voice/setup.py`, `pro/commands/voice_setup.py`; the test suite runs with the variable set |
| Accidental deletion | Deletion is dry-run unless `--apply` is passed | [write-model.md](write-model.md) |

## Not mitigated, or not evidenced

- **Prompt injection from mined issue text.** [SECURITY.md](../../SECURITY.md) lists it as in
  scope. There is no dedicated test corpus, so no claim of resistance is made.
- **A compromised local machine or compromised dependencies.** Out of scope; dependency scanning
  and CodeQL run in CI but their results are not summarized here.
- **Third-party sources being wrong.** Research output is ranked and validated, not proven true.

See [trust-boundaries.md](trust-boundaries.md) for where each input enters and
[../evaluations/security.md](../evaluations/security.md) for how to run the tests.
