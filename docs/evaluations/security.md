# Security evaluation

**Measured.** Unit-level behavior of security-relevant code paths. There is no adversarial
benchmark and no third-party penetration test.

**Covered by tests.**

| Behavior | Tests |
|---|---|
| Offline secrets scan finds a credential and redacts it in the report | `tests/test_secrets_scanner.py` |
| Security templates for scaffolds are generated | `tests/test_security_templates.py` |
| Path traversal is blocked in scaffold generation and mitigation checks | `tests/test_scaffold_generator.py`, `tests/test_mitigation_enforcer.py` |
| Research output paths are validated | `tests/test_research_validator.py` |
| Source hosts are matched on the parsed host, so spoofed URLs do not match | `tests/test_urls.py` |
| The suite never installs packages | runs with `GENESIS_NO_AUTO_INSTALL=1` |

**Reproduce.**

```bash
GENESIS_NO_AUTO_INSTALL=1 pytest tests/test_secrets_scanner.py tests/test_security_templates.py tests/test_urls.py tests/test_research_validator.py tests/test_mitigation_enforcer.py tests/test_scaffold_generator.py -q
```

**Expected.** All pass.

**Other automated checks.** CodeQL, secret scanning and dependency scanning run from
`.github/workflows/`. Their results are on the GitHub Actions page and are not recorded here.

**Limitations.**

- No fuzzing, no red-team corpus, and no measured detection rate for the secrets scanner.
- Prompt injection is listed as in scope in [SECURITY.md](../../SECURITY.md), but there is no
  dedicated injection test corpus.
- `docker/capability_audit.py` checks advertised capabilities against a PyPI install. One check
  there ("pitfall ranker rejects a spoofed source host") is a known failure of that audit script;
  the unit test for the same behavior is in `tests/test_urls.py`.
- What is in and out of scope: [threat-model](../security/threat-model.md).
