"""Genesis Architect CLI - genesis init / genesis config / genesis companion."""

import typer
from typing import Optional
from pathlib import Path

app = typer.Typer(
    name="genesis",
    help="Research first. Build once. Scans real GitHub repos before scaffolding.",
    no_args_is_help=True,
)


def _ask_confirm(prompt: str) -> bool:
    raw = typer.prompt(prompt + " [y/n]").strip().lower()
    return raw in ("y", "yes", "כן", "yes")


@app.command()
def init(
    vision: Optional[str] = typer.Argument(None, help="What you want to build"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="LLM model to use"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name"),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Primary language (python, typescript, go, rust, ...)"),
):
    """Scan GitHub repos, mine pitfalls, and scaffold your project."""
    from genesis_architect import config as cfg
    from genesis_architect.core import github, llm, scaffolder
    from genesis_architect.core import audit_inference, nlu_gate, vault
    from genesis_architect.core.github import GitHubRateLimitError

    github_token = cfg.get("GITHUB_TOKEN")
    llm_api_key = cfg.get("LLM_API_KEY")

    if not llm_api_key:
        typer.echo("No LLM API key found. Run: genesis config set LLM_API_KEY <your-key>", err=True)
        raise typer.Exit(1)

    # --- Phase 0: Audit inference - read project context from existing files ---
    cwd = Path.cwd()
    inferred = audit_inference.infer_project_context(cwd)

    if not vision:
        if inferred["description"]:
            typer.echo(f"\nDetected project: {inferred['description']}")
            vision = inferred["description"]
        else:
            vision = typer.prompt("Describe what you want to build")

    project_name = name or (inferred["name"] if inferred["name"] else vision.lower().replace(" ", "_")[:20])
    out_dir = output or project_name

    typer.echo(f"\nGenesis Architect - researching: {vision}\n")

    # --- Phase 1: GitHub scan ---
    typer.echo("Phase 1: Scanning GitHub repositories...")
    try:
        repos = github.search_repos(vision, token=github_token, limit=15, language=language)
    except GitHubRateLimitError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    if not repos:
        typer.echo("No repos found. Try a different vision description.", err=True)
        raise typer.Exit(1)
    for r in repos[:5]:
        typer.echo(f"  {r['name']} ({r['stars']} stars)")
    typer.echo(f"  ... and {max(0, len(repos) - 5)} more\n")

    # --- Phase 2: Issue mining ---
    typer.echo("Phase 2: Mining GitHub Issues for pitfalls...")
    all_issues = []
    for repo in repos[:5]:
        try:
            issues = github.fetch_issues(repo["name"], token=github_token)
            all_issues.extend(issues)
        except GitHubRateLimitError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1)
    typer.echo(f"  Found {len(all_issues)} issues to analyze\n")

    # --- Phase 3: Resolve known pitfalls from vault ---
    typer.echo("Phase 3: Checking knowledge vault for known solutions...")
    vault_hit = vault.get(vision, cwd)
    if vault_hit and not vault.is_stale(vault_hit):
        typer.echo(f"  Cached solution found (from {vault_hit.get('source_url', 'vault')})\n")
    else:
        typer.echo("  No cache hit - will generate fresh analysis\n")

    # --- Phase 4: Architecture choice via NLU ---
    typer.echo("Phase 4: Choose your architecture:\n")
    typer.echo("  A) Minimalist - simple, small, easy to maintain")
    typer.echo("  B) Scalable   - full production setup, CI/CD, modular")
    typer.echo("  C) Quick      - fastest possible scaffold, minimal config")
    typer.echo("  D) Hybrid     - mix of minimalist core + scalable extensions\n")

    ask_fn = lambda: typer.prompt("Your choice (A/B/C/D or describe in words)")
    confirm_fn = lambda: _ask_confirm("Confirm")
    arch_choice = nlu_gate.prompt_choice(ask_fn, confirm_fn)

    if arch_choice == "__restart__":
        typer.echo("\nStarting over from the beginning...")
        raise typer.Exit(0)

    arch_labels = {"A": "Minimalist", "B": "Scalable", "C": "Quick", "D": "Hybrid"}
    typer.echo(f"\n  Building {arch_labels.get(arch_choice, arch_choice)} scaffold...\n")

    # --- Phase 5: LLM analysis + scaffold ---
    typer.echo("Phase 5: Analyzing with LLM and generating scaffold...")
    llm_fn = lambda prompt: llm.ask(prompt, model=model, api_key=llm_api_key)

    created = scaffolder.generate(out_dir, vision, project_name, repos, all_issues, llm_fn)

    # Store result in vault for future runs
    if created:
        vault.put(vision, f"scaffold at {out_dir}", f"local:{out_dir}", cwd)

    typer.echo("\nGenesis Architect complete.\n")
    for f in created:
        typer.echo(f"  Created: {f}")
    typer.echo(f"\nNext: cd {out_dir} and review RESEARCH.md and PITFALLS.md")
    typer.echo("\nRun `genesis companion` to stay in active development mode.")


@app.command()
def companion(
    project_path: Optional[str] = typer.Argument(None, help="Project path (default: current dir)"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="LLM model to use"),
):
    """Stay active after scaffold - answers questions, detects when to exit."""
    from genesis_architect import config as cfg
    from genesis_architect.core import companion as comp
    from genesis_architect.core import llm, audit_inference, resolve_engine

    llm_api_key = cfg.get("LLM_API_KEY")
    if not llm_api_key:
        typer.echo("No LLM API key found. Run: genesis config set LLM_API_KEY <your-key>", err=True)
        raise typer.Exit(1)

    cwd = Path(project_path) if project_path else Path.cwd()
    inferred = audit_inference.infer_project_context(cwd)
    project_name = inferred.get("name") or cwd.name

    typer.echo(f"\nGenesis Companion active for: {project_name}")
    typer.echo("Ask questions about your project. Type 'done' or 'exit' to quit.\n")

    system_prompt = (
        f"You are a development companion for a project called '{project_name}'. "
        f"Project context: {inferred.get('description', '')}. "
        f"Give concise, practical answers. Remember what the user said earlier in this session."
    )
    history: list[dict] = [{"role": "user", "content": system_prompt}, {"role": "assistant", "content": "Understood. I'm ready to help with your project."}]

    while True:
        try:
            user_input = typer.prompt(f"[{project_name}]")
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nCompanion mode closed.")
            break

        should_exit, reason = comp.should_exit(user_input)
        if should_exit:
            typer.echo(comp.exit_message(reason))
            break

        # Check vault first
        cached = resolve_engine.resolve_with_output(user_input, str(cwd))
        if cached.strip():
            typer.echo(f"\n{cached}\n")
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": cached.strip()})
        else:
            response = llm.ask(user_input, model=model, api_key=llm_api_key, history=history)
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": response})
            typer.echo(f"\n{response}\n")


@app.command()
def publish(
    project_path: Optional[str] = typer.Argument(None, help="Project root (default: current dir)"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="LLM model to use"),
):
    """Generate Show HN post and GitHub Release notes, with copy-paste and browser AI options."""
    from genesis_architect import config as cfg
    from genesis_architect.core import llm
    from genesis_architect.core import publish_agent

    llm_api_key = cfg.get("LLM_API_KEY")
    if not llm_api_key:
        typer.echo("No LLM API key found. Run: genesis config set LLM_API_KEY <your-key>", err=True)
        raise typer.Exit(1)

    cwd = Path(project_path) if project_path else Path.cwd()
    typer.echo("\nGenesis Publish - collecting release data...")

    data = publish_agent.collect_release_data(cwd)
    typer.echo(f"  Version: {data['version']}")
    typer.echo(f"  Commits found: {len(data['commits'])}")
    typer.echo(f"  Tests: {data['test_count']}")
    psr = data.get("psr_assets", {})
    if psr.get("replay_gif"):
        typer.echo(f"  PSR replay GIF: {psr['session_name']}/action_replay.gif")
    if psr.get("screenshots"):
        typer.echo(f"  PSR screenshots: {len(psr['screenshots'])} key frames found")
    typer.echo("\nGenerating content with LLM...")

    llm_fn = lambda prompt: llm.ask(prompt, model=model, api_key=llm_api_key)
    content = publish_agent.generate_publish_content(data, llm_fn)

    typer.echo(publish_agent.format_output(content, version=data["version"], psr_assets=psr))


@app.command()
def config(
    action: str = typer.Argument(..., help="'set', 'get', or 'show'"),
    key: Optional[str] = typer.Argument(None, help="Key name (e.g. GITHUB_TOKEN, LLM_API_KEY)"),
    value: Optional[str] = typer.Argument(None, help="Value to set"),
):
    """Manage API keys. Use: genesis config set LLM_API_KEY <key>"""
    from genesis_architect import config as cfg

    if action == "set":
        if not key or not value:
            typer.echo("Usage: genesis config set <KEY> <value>", err=True)
            raise typer.Exit(1)
        cfg.set_key(key, value)
        typer.echo(f"Saved {key}.")
    elif action == "get":
        if not key:
            typer.echo("Usage: genesis config get <KEY>", err=True)
            raise typer.Exit(1)
        val = cfg.get(key)
        typer.echo(val or f"{key} not set.")
    elif action == "show":
        for k, v in cfg.show().items():
            typer.echo(f"  {k}: {v}")
    else:
        typer.echo(f"Unknown action: {action}. Use set / get / show.", err=True)
        raise typer.Exit(1)


def main():
    app()


if __name__ == "__main__":
    main()
