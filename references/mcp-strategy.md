# MCP Usage Strategy for Genesis Architect

## Tool Priority Order

Always attempt tools in this order. If one fails, move to the next without blocking the workflow.

1. **GitHub MCP** - deep structural analysis, issue scanning, code reading
2. **Exa MCP** - broad ecosystem search (Reddit, HN, StackOverflow, blogs)
3. **Firecrawl MCP** - scrape specific pages (docs, README deep content)
4. **Web search** - general fallback

## GitHub MCP Usage

### Repository discovery
Search for repos matching the project domain. Apply filters:
- stars: >=100 (niche) or >=1000 (general infrastructure)
- pushed: >=one year ago (active projects only)
- language: match user preference if specified

### Deep analysis (top 3 to 5 repos)
For each repo, extract:
- Directory structure (file tree, 2 levels deep)
- Main entry point and its imports (reveals architectural pattern)
- Package manifest (package.json, pyproject.toml, Cargo.toml, etc.)
- README architecture section if present

### Issue scanning
Query: last 50 issues, both open and closed.
Sort by: comments (most discussed = most painful)
Look for labels: bug, architecture, performance, breaking-change

Extract patterns:
- Same error type appearing in 3+ issues = confirmed pitfall
- Issues closed with "by design" = architectural constraint to be aware of
- Issues with "wontfix" = known limitation

## Exa MCP Usage

Search queries to run in parallel:
1. "[project type] best practices [year]"
2. "[project type] common mistakes reddit"
3. "[project type] architecture discussion hacker news"
4. "[framework] pitfalls stackoverflow"

Target domains: reddit.com, news.ycombinator.com, stackoverflow.com, dev.to, medium.com

## Firecrawl MCP Usage

### scrape — always use these options to avoid token overflow
```json
{
  "url": "<target>",
  "onlyMainContent": true,
  "formats": ["markdown"],
  "excludeTags": ["nav", "footer", "header", "aside", "script", "style"]
}
```
Without `onlyMainContent: true`, pages like npm registry return 200K+ chars and exceed limits.
With it, the same page returns ~2K chars of relevant content.

### search — use for competitive landscape scans
```json
{
  "query": "<terms>",
  "limit": 10,
  "scrapeOptions": { "onlyMainContent": true, "formats": ["markdown"] }
}
```

### batch_scrape — use when scraping 3+ URLs from Phase 2 repo list
```json
{
  "urls": ["https://...", "https://...", "https://..."],
  "options": {
    "onlyMainContent": true,
    "formats": ["markdown"],
    "excludeTags": ["nav", "footer", "header", "aside", "script", "style"]
  }
}
```
More efficient than sequential scrape calls. Use when you have a known list of repo README or docs URLs to process in Phase 2.

### When to use Firecrawl vs Exa
| Goal | Use |
|------|-----|
| Find repos by category | Exa (`category: "github"`) |
| Read a specific doc page | Firecrawl scrape |
| Broad ecosystem news/blogs | Exa search |
| Scrape multiple pages in batch | Firecrawl batch_scrape |

## Fallback Logic

```
GitHub MCP available?
  YES: Use for repo discovery and issue scanning
  NO: Use Exa to find GitHub links, then Firecrawl to scrape them

Exa available?
  YES: Use for broad ecosystem search
  NO: Use web search with same queries

All MCPs unavailable?
  Use web search for everything
  Note in RESEARCH.md: "Analysis based on web search only - GitHub deep scan unavailable"
```

## Reporting Tool Failures

When a tool fails, report briefly and continue:
> "[In the user's language] GitHub MCP unavailable - falling back to web search..."

Never stop the workflow for a tool failure. Always degrade gracefully.

## OSV.dev CVE Check

Use for deterministic CVE detection in Phase 2 Ecosystem Velocity Scoring and Phase 7 `genesis check`.

### API - no key required, no rate limit for basic queries
```json
POST https://api.osv.dev/v1/query
{
  "package": {
    "name": "[package-name]",
    "ecosystem": "[PyPI|npm|Go|crates.io|RubyGems]"
  }
}
```

Returns: list of vulnerabilities with CVE IDs, severity, affected versions, and fixed versions.

### When to use
| Phase | Use |
|-------|-----|
| Phase 2 Ecosystem Velocity Scoring | Query top 3 dependencies found in analyzed repos |
| Phase 7 `genesis check` | Query all dependencies in generated scaffold |

### Output format
Show as one-line signals alongside Ecosystem Velocity:
```
🔴 requests==2.28.0: CVE-2024-35195 (HIGH) - fix: upgrade to 2.32.0
✅ fastapi: no known CVEs
```
