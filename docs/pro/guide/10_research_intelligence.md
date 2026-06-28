# Research Intelligence Engine

**Pro (Free has basic GitHub + Docs research).** Genesis researches like a senior
engineer: it plans, searches in priority order, cross-checks, and produces an
[Evidence Pack](12_evidence_packs.md).

## The pipeline

1. Classify the request and technical domain.
2. Ask only the missing questions needed to align.
3. Build a research plan with source categories + priority.
4. Search **official docs first** when technical truth matters.
5. Search source code, issues, PRs, releases, changelogs.
6. Search security databases when dependencies / production risk are involved.
7. Search Stack Overflow / Stack Exchange for recurring problems.
8. Use Reddit + Reddit Answers for [field intelligence](11_field_intelligence.md).
9. Use YouTube transcripts + conference talks for long-form learning.
10. Detect contradictions between sources.
11. Rank evidence by reliability and recency.
12. Produce an Evidence Pack: source table, confidence, disagreements,
    recommendation.

## Source priority (Engineering Source Intelligence)

| Category | Sources | Reliability |
|----------|---------|:-----------:|
| Official Truth | Official/API/SDK docs, RFCs, specs | 100 |
| Source Truth | GitHub source, issues, PRs, releases, changelogs, git history | 95–99 |
| Security | GH Advisories, CVE, NVD, OSV | 98 |
| Q&A | Stack Overflow / Exchange | 90 |
| Developer Field | Reddit, Reddit Answers, HN, Lobsters | 80–90 |
| Packages | PyPI, npm, crates.io, Maven, NuGet | 88 |
| Learning | YouTube, conference talks | 70–82 |
| Local Project | Source, tests, CI logs, TODO/FIXME | 99 |

The full ranked list lives in the [Source Registry](13_source_registry.md), and
new sources can be added without changing the engine.
