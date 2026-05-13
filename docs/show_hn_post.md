# Show HN: Genesis Architect - Claude skill that researches GitHub repos before scaffolding

**Title (60 chars):**
Show HN: Claude skill that mines GitHub Issues before scaffolding

---

**Post body:**

Most scaffolding tools give you boilerplate. Genesis Architect gives you boilerplate built to avoid the mistakes others already hit.

Before writing a single file, it:
1. Scans 15-20 real GitHub repos matching your project type
2. Mines their Issues for what broke in production (ranked by engagement: comments + reactions)
3. Synthesizes a "wise average" of proven folder structures
4. Builds your scaffold with those specific pitfalls already mitigated

The output isn't just files - it's a RESEARCH.md with the repos analyzed, a PITFALLS.md with citations to the real GitHub issues, and architecture comments in the code that say "this structure avoids pitfall #2" with a link.

It's a Claude Code skill - runs inside Claude Code as a native workflow. No separate server, no API keys beyond what Claude Code already uses.

The part I find most useful: after scaffolding it stays in companion mode. "genesis check" queries OSV.dev for CVEs in your deps. "genesis resolve [problem]" checks a local vault first, then hits Stack Overflow. "genesis audit ." runs the research phase on an existing codebase.

It's MIT licensed, has a CI pipeline (Gitleaks, Snyk, SonarCloud, CodeQL), and the scaffold it generates includes all of those from day one.

GitHub: https://github.com/maioio/genesis-architect

Happy to answer questions about the implementation or the Claude Code skill format.

---

**Timing:** Post Monday or Tuesday 8-10am US Eastern
**Subreddit crosspost:** r/ClaudeAI, r/programming, r/SideProject
