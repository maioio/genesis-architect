# Open Source Intelligence - Genesis Architect

Genesis researches real open-source projects before building anything.
This document describes what Genesis looks for and where.

---

## What Genesis Researches

For every new project, Genesis analyzes:

- **Real repositories** - 15-20 active open-source projects similar to what you are building
- **Real failures** - bugs, architecture regrets, and breaking changes from GitHub Issues
- **Ecosystem health** - whether the libraries you will depend on are maintained and secure
- **Community signals** - discussions on Reddit, Hacker News, and StackOverflow about the same problem space

The goal is to find what went wrong for others, so your project starts with those problems already solved.

---

## Research Sources

| Source | What it provides | When used |
|--------|-----------------|-----------|
| GitHub | Repository structure, issue history, architectural patterns | All projects |
| Reddit / Hacker News | Community experience, war stories, tool comparisons | All projects |
| StackOverflow | Common errors, accepted solutions | All projects |
| OSV.dev | Known CVEs for dependencies | All projects |
| PyPI | Package release activity | Python projects |
| npm | Package download stats, release dates | JS/TS projects |
| crates.io | Crate activity and adoption | Rust projects |
| Context7 | Official library docs | When a specific library is under evaluation |

---

## Research Quality Levels

Genesis reports one of three quality levels before building:

- **FULL** - GitHub MCP available, 8+ repos deep-analyzed, 5+ issues found
- **PARTIAL** - some sources unavailable or fewer repos found
- **THIN** - web search only, limited data

THIN does not block the build - you decide whether to proceed.

---

## What Genesis Does With the Research

1. Finds the most common folder structure across similar projects
2. Identifies recurring bugs and architecture mistakes (pitfalls)
3. Checks whether key dependencies are actively maintained and CVE-free
4. Uses all of this to generate a scaffold where known problems are already mitigated

The pitfalls are not just documented - they become real code and real tests.

---

## Sources Not Used

Genesis does not use: Sourcegraph, Forgejo, Gitea, Codeberg, Hugging Face, ArXiv, NVD/NIST directly, or vendor marketing content.

Excluded because: either redundant with included sources, too noisy, or not relevant to general software scaffolding.
