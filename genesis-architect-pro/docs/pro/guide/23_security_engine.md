# Security Engine

Threat modeling, secrets awareness, dependency CVEs, and hardening guidance
(basics in **Free**, depth + CVE validation in **Pro**).

## Capabilities

- **Threat model templates** — STRIDE + OWASP scaffolding generated for the
  project.
- **Dependency / CVE checks** — packages cross-referenced against security
  databases (CVE, NVD, OSV). Pro validates and connects findings into the
  [Knowledge Graph](25_knowledge_graph.md) as `cve → package → module` chains.
- **Hardening guidance** — concrete, prioritized recommendations.

## Worked example

```python
from genesis_architect_pro.security_templates import generate_security_docs
docs = generate_security_docs(".", stride=True, owasp=True)
# docs is a dict of {filename: markdown}
```

## Why it connects to recovery

A CVE in isolation is just a number. Linked through the Knowledge Graph to the
modules that actually use the vulnerable package — and cross-referenced with
do-not-touch risk zones — it becomes an actionable, prioritized fix. See
[Recovery](21_recovery_engine.md) and [Knowledge Graph](25_knowledge_graph.md).
