"""Genesis Architect - Research first. Build once."""

from pathlib import Path

__version__ = "5.4.1"


def scaffold(vision: str, output_dir: str | Path, *, name: str | None = None,
             model: str = "claude-sonnet-4-6", language: str | None = None) -> Path | None:
    """Non-interactive scaffold entry point — no prompts, sensible defaults.

    This is the same Phase 1/2/5 pipeline `genesis init` runs (scan repos,
    mine issues, generate with an LLM), minus Phase 3's vault-cache lookup
    and Phase 4's interactive architecture-choice prompt (which — same as in
    `init` — doesn't currently change generation output; it's echoed back to
    the user but never passed into scaffolder.generate()). Used by genesis-
    architect-pro's BUILD mode (`genesis decide "build ..."`), which runs
    inside a GDE session with no terminal to prompt against. For the full
    interactive experience, use `genesis init`.

    Raises RuntimeError on any unrecoverable failure (no LLM key, no repos
    found, GitHub rate limit) — never a raw exception from a third-party
    SDK. Returns the output directory, or None if nothing was created.
    """
    from genesis_architect import config as cfg
    from genesis_architect.core import github, llm as llm_module, scaffolder
    from genesis_architect.core.github import GitHubRateLimitError

    llm_api_key = cfg.get("LLM_API_KEY")
    if not llm_api_key:
        raise RuntimeError(
            "No LLM API key found. Run: genesis config set LLM_API_KEY <your-key>")

    github_token = cfg.get("GITHUB_TOKEN")
    project_name = name or vision.lower().replace(" ", "_")[:20]
    out_dir = Path(output_dir)

    try:
        repos = github.search_repos(vision, token=github_token, limit=15, language=language)
    except GitHubRateLimitError as exc:
        raise RuntimeError(str(exc)) from exc
    if not repos:
        raise RuntimeError(f"No GitHub repos found for '{vision}'. Try a more specific vision.")

    all_issues: list[dict] = []
    for repo in repos[:5]:
        try:
            all_issues.extend(github.fetch_issues(repo["name"], token=github_token))
        except GitHubRateLimitError:
            break  # non-interactive: partial issue data is fine, don't hard-fail on rate limit

    def llm_fn(prompt: str) -> str:
        return llm_module.ask(prompt, model=model, api_key=llm_api_key)

    try:
        created = scaffolder.generate(str(out_dir), vision, project_name, repos, all_issues, llm_fn)
    except llm_module.LLMError as exc:
        raise RuntimeError(str(exc)) from exc

    return out_dir if created else None
