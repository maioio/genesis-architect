# MCP Usage Strategy for Genesis Architect

## Tool Priority Order

Always attempt tools in this order. If one fails, move to the next without blocking the workflow.

1. **GitHub MCP** - deep structural analysis, issue scanning, code reading
2. **Last30Days skill** (if installed) - Stream B ecosystem search: covers Reddit, HN, GitHub, Polymarket in parallel, ranked by real engagement. Use `/last30days [vision] pitfalls` and `/last30days [vision] architecture mistakes`. Falls back to Exa if unavailable.
3. **Exa MCP** - broad ecosystem search (Reddit, HN, StackOverflow, blogs). Used when Last30Days unavailable.
4. **Context7 MCP** (conditional) - library-specific docs. Use only when user asks about a specific library and official docs are relevant to architecture decision. Never in Phase 2 baseline scan.
5. **Firecrawl MCP** - scrape specific pages (docs, README deep content)
6. **Web search** - general fallback

## Token Optimization

If **context-mode MCP** is active, large GitHub MCP outputs are automatically indexed in SQLite FTS5 and summarized before reaching Claude. No action needed - it activates via hooks. Particularly effective in Phase 2 (repo scanning) and Phase 7 (`genesis check`).

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

### scrape: always use these options to avoid token overflow
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

### search: use for competitive landscape scans
```json
{
  "query": "<terms>",
  "limit": 10,
  "scrapeOptions": { "onlyMainContent": true, "formats": ["markdown"] }
}
```

### batch_scrape: use when scraping 3+ URLs from Phase 2 repo list
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

## Video Research (Stream D)

Used in Phase 2 and Companion Mode `genesis research --video`.

### Phase 2 - metadata only (no token cost)

Run three Exa queries in parallel with Streams A/B:
```
"[vision] lessons learned mistakes site:youtube.com"
"[vision] architecture talk conference site:youtube.com"
"[vision] production failure postmortem site:youtube.com"
```
Extract per result: title, channel/author, url, snippet (max 300 chars).
Classify signal type: lessons_learned > architecture_talk > tutorial > unknown.
Cap output at 5 videos. Show in Phase 5 with ready-to-run `/watch` commands.
Never transcribe during Phase 2 baseline.

### Companion Mode - deep analysis

Triggered only by `genesis research --video <url>`.
Auto-setup (Pro): call `video_research.ensure_watch_ready()` before analysis. It
auto-installs yt-dlp + ffmpeg via the /watch skill's setup.py (winget/brew/pip,
silent - the user does nothing). It returns `ready`, `key_provider`, and, if a
transcription key is still missing, `action_needed` with exact next steps.
- Transcription key precedence (resolve_transcription_key): `GENESIS_WHISPER_KEY`
  (managed quota, free tier then billed) -> `GROQ_API_KEY` (BYOK, free) -> `OPENAI_API_KEY`.
- The key is the one piece that cannot be auto-provisioned on the client: a
  managed key needs a Genesis proxy, a BYOK key must be created by the user.
  Never embed a managed key in the shipped package.
- Config file fallback: `~/.config/watch/.env`

On success, invoke `/watch` with this question template:
> "Analyze this video for: (1) architecture decisions and their rationale, (2) pitfalls and mistakes mentioned, (3) lessons learned about [topic]. Extract specific, actionable insights."

Output format: cite timestamps, extract pitfall candidates, add to `.genesis/vault/` if confirmed useful.

### Signal type priority

| Type | Icon | Relevance | Why |
|------|------|-----------|-----|
| lessons_learned | 🎯 | high | Direct pitfall signal |
| architecture_talk | 🎯 | high | Design decisions from practitioners |
| tutorial | 📺 | medium | Setup patterns, common configs |
| unknown | 📎 | low | Show but don't highlight |

### Dependencies (not part of Genesis scaffold)

`yt-dlp`, `ffmpeg` - local binaries. GROQ_API_KEY or OPENAI_API_KEY - for Whisper transcription.
Source: `bradautomates/claude-video` (MIT). Genesis integrates via `/watch` skill invocation - does not bundle the code.

---

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

## Normalized Result Schema

Every source adapter returns results in this format. Never pass raw tool output directly to Phase 3 - always normalize first.

```
source:       github_issues | reddit | hn | stackoverflow | exa_blog | pypi | npm | crates_io | osv
url:          canonical link to the original finding
confidence:   high | medium | low
signal_type:  pitfall | architecture_regret | security | performance | popularity | maintenance
raw_text:     extracted relevant excerpt (max 500 chars)
```

**Confidence assignment:**
| Source | Default confidence | Upgrade condition |
|--------|-------------------|-------------------|
| GitHub Issues (5+ comments) | high | 10+ reactions -> high |
| GitHub Issues (<5 comments) | medium | - |
| HN / Reddit thread | medium | 50+ points -> high |
| StackOverflow answer | medium | accepted answer -> high |
| Blog / dev.to | low | - |
| PyPI / npm stats | high | informational only |
| OSV.dev CVE | high | always |

**Deduplication:** when the same pitfall appears in 2+ sources, merge into one result and set confidence: high regardless of individual source confidence. Note: `corroborated_by: [url1, url2]`.

---

## Pro Multi-Source Default

With `genesis-architect-pro`, Phase 2 and `genesis research` default to multi-source. The goal is the best research in the market without burning time or money on every run. Two tiers:

**Fast tier - always runs in parallel (Pro default):**
- GitHub (repos + issues) - Stream A/C
- Exa ecosystem search - Stream B (targets reddit.com, news.ycombinator.com, stackoverflow.com)
- YouTube + Reddit metadata via Exa - Stream D (metadata only, no scrape, no transcription)

The fast tier is cheap: no paid scrapers, no API keys beyond what is already configured. It runs on every Pro research call.

**Heavy tier - escalates only on demand:**
- Reddit thread scrape (Apify) - escalate when the fast tier returns fewer than 3 high/medium pitfall candidates, OR the user asks to "go deeper" on a Reddit result.
- Instagram (Apify) - escalate only when the project is visual: UI, mobile app, game, design tool, brand. Skip entirely for CLIs, APIs, infra, libraries. Detect from vision text: `app`, `UI`, `design`, `game`, `mobile`, `frontend`, `brand`, `visual`.

Routing for the heavy tier: Reddit and Instagram are blocked by Exa and the
built-in web search, so use **`firecrawl_search`** for them (verified live: it
returns real reddit.com and instagram.com results, ~2 credits/query). Feed its
results through `video_research.firecrawl_to_exa_shape()` before
`parse_exa_results()`. Apify/Playwright remain options for deeper thread scraping
when firecrawl_search is not enough. Never auto-run the heavy tier on trivial
projects - the overhead exceeds the value.

**Free tier:** GitHub + Exa only. No YouTube/Reddit/Instagram defaults. This is the Pro differentiator.

**Reporting:** in Phase 5, label each finding with its source platform so the user sees the multi-source coverage. When the heavy tier is skipped, note why in one line: "Instagram skipped - non-visual project" or "Reddit deep-scrape skipped - fast tier had enough signal".

**Cost honesty:** never silently run a paid scraper. If escalation to Apify would incur cost on a borderline call, surface it: "Fast tier was thin - run Apify Reddit deep-scrape? (paid)".

---

## Source Selection Rules

Apply these rules before deciding which sources to query. Do not query all sources on every run.

**Always query (Phase 2 baseline):**
- GitHub MCP - repo discovery + issue scan
- Exa or Last30Days - ecosystem context

**Pro fast tier (default, see "Pro Multi-Source Default"):**
- YouTube + Reddit metadata via Exa - always, metadata only

**Pro heavy tier (escalate on demand only):**
- Reddit deep-scrape (Apify) - when fast tier is thin or user asks to go deeper
- Instagram (Apify) - visual/design projects only

**Query when language matches:**
- PyPI API - Python projects only
- npm API - JS/TS projects only
- crates.io API - Rust projects only

**Query conditionally:**
- Context7 - only when a specific library name appears in Phase 1 answers and docs are architecture-relevant
- OSV.dev - always for Ecosystem Velocity Scoring, for top 3 deps found in analyzed repos
- Hugging Face Hub API (Stream E) - only when the project vision involves AI/ML models, embeddings, NLP, vision, audio, or similar (detected from Phase 1 answers or vision text)

**Never query:**
- Sourcegraph, Forgejo, Gitea, Codeberg (rejected by committee)
- dev.to / Medium directly (covered by Exa target domains)
- NVD / NIST directly (OSV.dev aggregates these)

**Domain noise filter:** skip results from: medium.com listicles with no code, vendor marketing pages, tutorial sites with no issue history.

---

## Ranking Rules

Apply after normalizing all results. Higher score = shown earlier in pitfall candidates.

**Base score per result:**
- confidence: high = 3 pts, medium = 2 pts, low = 1 pt

**Bonuses:**
- Recency: issue/post from last 12 months = +2, last 24 months = +1, older = 0
- Cross-source corroboration: same pitfall in 2+ sources = +3
- Engagement: 10+ comments or reactions = +1

**Result:** sort pitfall candidates by score descending before Phase 3 synthesis. Show top 10 max to avoid token overflow.

---

## Stable Technical Evidence vs Recent Signal

When presenting research findings (Phase 5), separate results into two categories:

**Stable Technical Evidence** - durable, verifiable facts:
- Official docs, verified code evidence, GitHub issues/PRs, changelogs, security advisories (OSV.dev), package registry data.

**Recent Signal** - time-sensitive community/market evidence:
- Stream B (Last30Days/Exa) ecosystem findings and Stream D (video) results - Reddit/HN discussions, recent posts, conference talks. Reflects current sentiment but decays in relevance.

**Rule:** Recent Signal must never override or contradict Stable Technical Evidence. If a Recent Signal item conflicts with official docs, verified code, GitHub issues, changelogs, or security advisories, the Stable Technical Evidence wins and the conflict should be noted, not silently resolved in favor of the recent finding.

---

## Adapter Interface

Every source follows this pattern. On failure: log briefly, return empty list, never block.

```
available() -> bool          # check if MCP/API is reachable
search(query) -> [Result]    # normalized results only
```

Fallback chain per adapter type:
```
Repo search:   GitHub MCP -> Exa (category: github) -> Firecrawl scrape
Ecosystem:     Last30Days -> Exa -> web search
Docs:          Context7 -> Firecrawl scrape -> web search
Package stats: PyPI/npm/crates.io API -> Firecrawl scrape of registry page
CVE:           OSV.dev API (no fallback needed - public, reliable)
HF models:     HF Hub API -> Firecrawl scrape of huggingface.co page
Reddit deep:   Apify -> Playwright (never Firecrawl - fails on reddit.com)
Instagram:     Apify -> Playwright (never Firecrawl - fails on instagram.com)
```

---

## Package Registry Adapters

Use during Ecosystem Velocity Scoring in Phase 2. No API key required for any of these.

### PyPI (Python projects only)

```
GET https://pypi.org/pypi/{package}/json
```
Extract: `info.version`, `info.requires_python`, `releases` (count last 6 months = activity signal).
Signal: if 0 releases in 6 months -> `⚠ {package}: no PyPI releases in 6 months`.

### npm (JS/TS projects only)

```
GET https://registry.npmjs.org/{package}
GET https://api.npmjs.org/downloads/point/last-month/{package}
```
Extract: `dist-tags.latest`, `time` (last publish date), monthly downloads.
Signal: if downloads < 1000/month for a core dependency -> `⚠ {package}: low adoption ({N}/month)`.

### crates.io (Rust projects only)

```
GET https://crates.io/api/v1/crates/{package}
```
Extract: `crate.newest_version`, `crate.updated_at`, `crate.downloads`.
Signal: same pattern as PyPI.

### GitLab (stub - future)

Not implemented. When a Phase 2 search returns gitlab.com URLs, scrape them via Firecrawl as fallback. Full GitLab MCP adapter deferred.

---

## Hugging Face Adapter (Stream E)

Used in Phase 2 only when the project vision involves AI/ML: model inference, embeddings, NLP, vision, audio, fine-tuning, RAG, or similar. Skip entirely for non-ML projects (CLIs, web apps, infra tools with no model usage).

### Detection

Trigger Stream E if Phase 1 vision text matches: `model`, `inference`, `embedding`, `LLM`, `transformer`, `classif`, `dataset`, `fine-tun`, `NLP`, `vision`, `speech`, `audio`, `RAG`, `vector search`.

### API - no key required for public read endpoints

```
GET https://huggingface.co/api/models?search={query}&sort=downloads&limit=5
GET https://huggingface.co/api/datasets?search={query}&sort=downloads&limit=5
GET https://huggingface.co/api/spaces?search={query}&sort=likes&limit=3
GET https://huggingface.co/api/models/{model_id}  # full model card: license, gated, downloads, tags
```

Extract per model: `id`, `downloads`, `likes`, `tags`, `pipeline_tag`, `license`, `gated` (false | "auto" | "manual").

### Normalization

Map to the standard Result schema:
- `source: hf_models | hf_datasets | hf_spaces`
- `confidence: high` if downloads > 100k/month, else `medium`
- `signal_type: popularity` (or `gating` if `gated != false`)
- `raw_text`: model id + pipeline_tag + license + download count

### Phase 5 - gating/license signals

For any model surfaced as a recommended choice, show one-line signals:
```
✅ {model_id}: license={license}, ungated, {downloads}/month
⚠ {model_id}: gated={gated} - requires HF account approval before use
⚠ {model_id}: license={license} - verify compatible with project license
```

### Phase 7 - genesis research

`genesis research [topic]` includes Stream E results when the topic matches the AI/ML detection trigger above, ranked alongside repo/ecosystem results using the same Ranking Rules.

### Fallback

If `huggingface.co/api/*` is unreachable, scrape `https://huggingface.co/models?search={query}` via Firecrawl (`onlyMainContent: true`) as a degraded fallback. If both fail, skip Stream E silently and note in RESEARCH.md: "Hugging Face Hub unreachable - model research skipped."

---

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
