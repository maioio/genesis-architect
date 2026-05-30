"""Generates RESEARCH.md and PITFALLS.md from LLM analysis."""

from pathlib import Path

_RESEARCH_PROMPT = """\
You are Genesis Architect. Analyze these GitHub repositories for a project about: {vision}

Repositories found:
{repos}

Top issues found:
{issues}

Write a RESEARCH.md file with:
1. ## Summary - what the ecosystem looks like (3-5 sentences)
2. ## Analyzed Repositories - table with Name, Stars, Key insight
3. ## Architecture Decision Rationale - what approach to take and why
4. ## Common Patterns - what successful projects do

Be concrete and specific. Reference real repo names and issue titles.
"""

_PITFALLS_PROMPT = """\
You are Genesis Architect. Based on these GitHub issues for a project about: {vision}

Issues:
{issues}

Write a PITFALLS.md file listing the top 5 pitfalls found in real projects.
For each pitfall use this exact format:

## Pitfall N: [short name]
**Seen in**: [issue URL]
**Our mitigation**: [specific fix or approach]
mitigation_file_path: src/{name}/[relevant_file]

Be specific. Use real issue titles and URLs.
"""


def generate(output_dir: str, vision: str, name: str, repos: list[dict], issues: list[dict],
             llm_fn) -> list[str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    created = []

    repos_text = "\n".join(f"- {r['name']} ({r['stars']} stars): {r['description']}" for r in repos)
    issues_text = "\n".join(f"- [{i['title']}]({i['url']}): {i['body'][:200]}" for i in issues[:20])

    research = llm_fn(_RESEARCH_PROMPT.format(vision=vision, repos=repos_text, issues=issues_text))
    research_path = out / "RESEARCH.md"
    research_path.write_text(research, encoding="utf-8")
    created.append(str(research_path))

    pitfalls = llm_fn(_PITFALLS_PROMPT.format(vision=vision, issues=issues_text, name=name))
    pitfalls_path = out / "PITFALLS.md"
    pitfalls_path.write_text(pitfalls, encoding="utf-8")
    created.append(str(pitfalls_path))

    return created
