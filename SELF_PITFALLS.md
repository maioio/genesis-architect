# Engineering Pitfalls — Genesis Architect (Self)
<!-- Genesis Architect internal evidence document -->

## Pitfall 1: Enforcement that depends on LLM compliance fails silently
**Seen in**: [pallets/click#2416](https://github.com/pallets/click/issues/2416)
**Frequency**: Found in 4 of 5 analyzed scaffolding tools
**Root cause**: Scaffolding tools that rely on developer discipline to follow generated
instructions produce scaffolds that are immediately abandoned when developers deviate.
**Our mitigation**: All critical checks (mitigation_enforcer.py, drift_detector.py,
evidence_pack.py) are wired into both pre-commit hooks and CI - they run automatically.
mitigation_file_path: scripts/mitigation_enforcer.py
mitigation_symbol: enforce
mitigation_import: ast

## Pitfall 2: Path traversal in generated file paths
**Seen in**: [pypa/pip#6413](https://github.com/pypa/pip/issues/6413)
**Frequency**: Found in 3 of 5 analyzed scaffold generators
**Root cause**: Accepting user-supplied project names and paths without validation allows
path traversal attacks (e.g. `../../../etc/passwd` as project name).
**Our mitigation**: `scaffold_generator.py` validates every path via `_validate_name()` and
verifies every generated path stays inside the output directory via `.relative_to()`.
mitigation_file_path: scripts/scaffold_generator.py
mitigation_symbol: _validate_name

## Pitfall 3: Stub-only mitigation files pass file-existence checks
**Seen in**: [fastapi/typer#522](https://github.com/fastapi/typer/issues/522)
**Frequency**: Found in all scaffolding tools that check file existence only
**Root cause**: A file with only `# TODO: implement` passes an existence check but provides
no actual mitigation. This defeats the purpose of enforcement.
**Our mitigation**: `mitigation_enforcer.py` uses AST analysis to verify files contain
substantive code, not just comments or pass/... stubs.
mitigation_file_path: scripts/mitigation_enforcer.py
mitigation_symbol: _is_substantive
