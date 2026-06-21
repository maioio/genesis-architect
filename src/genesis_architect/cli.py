"""Genesis Architect CLI - genesis init / genesis config / genesis companion."""

from pathlib import Path

import typer

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
    vision: str | None = typer.Argument(None, help="What you want to build"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output directory"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="LLM model to use"),
    name: str | None = typer.Option(None, "--name", "-n", help="Project name"),
    language: str | None = typer.Option(None, "--language", "-l", help="Primary language (python, typescript, go, rust, ...)"),
):
    """Scan GitHub repos, mine pitfalls, and scaffold your project."""
    from genesis_architect import config as cfg
    from genesis_architect.core import audit_inference, github, llm, nlu_gate, scaffolder, vault
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

    def ask_fn():
        return typer.prompt("Your choice (A/B/C/D or describe in words)")
    def confirm_fn():
        return _ask_confirm("Confirm")
    arch_choice = nlu_gate.prompt_choice(ask_fn, confirm_fn)

    if arch_choice == "__restart__":
        typer.echo("\nStarting over from the beginning...")
        raise typer.Exit(0)

    arch_labels = {"A": "Minimalist", "B": "Scalable", "C": "Quick", "D": "Hybrid"}
    typer.echo(f"\n  Building {arch_labels.get(arch_choice, arch_choice)} scaffold...\n")

    # --- Phase 5: LLM analysis + scaffold ---
    typer.echo("Phase 5: Analyzing with LLM and generating scaffold...")
    def llm_fn(prompt):
        return llm.ask(prompt, model=model, api_key=llm_api_key)

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
    project_path: str | None = typer.Argument(None, help="Project path (default: current dir)"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="LLM model to use"),
):
    """Stay active after scaffold - answers questions, detects when to exit."""
    from genesis_architect import config as cfg
    from genesis_architect.core import audit_inference, llm, resolve_engine
    from genesis_architect.core import companion as comp

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
    project_path: str | None = typer.Argument(None, help="Project root (default: current dir)"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="LLM model to use"),
):
    """Generate Show HN post and GitHub Release notes, with copy-paste and browser AI options."""
    from genesis_architect import config as cfg
    from genesis_architect.core import llm, publish_agent

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

    def llm_fn(prompt):
        return llm.ask(prompt, model=model, api_key=llm_api_key)
    content = publish_agent.generate_publish_content(data, llm_fn)

    typer.echo(publish_agent.format_output(content, version=data["version"], psr_assets=psr))


@app.command()
def config(
    action: str = typer.Argument(..., help="'set', 'get', or 'show'"),
    key: str | None = typer.Argument(None, help="Key name (e.g. GITHUB_TOKEN, LLM_API_KEY)"),
    value: str | None = typer.Argument(None, help="Value to set"),
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


@app.command()
def research(
    topic: str = typer.Argument(..., help="Topic to research, or a video URL with --video"),
    video: bool = typer.Option(False, "--video", help="Deep video-to-pitfall analysis (Pro)"),
):
    """Research a topic. Use --video for Pro video-to-pitfall analysis."""
    from genesis_architect.core import pro_bridge

    if video:
        try:
            engine = pro_bridge.get_pro_module("video_research")
        except pro_bridge.ProUnavailable as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2)
        queries = engine.build_all_media_queries(topic)
        typer.echo("Pro video research queries built:")
        for platform, qs in queries.items():
            typer.echo(f"  {platform}: {len(qs)} queries")
        typer.echo("Run /watch on a chosen video, then extract pitfalls with Pro.")
        return

    from genesis_architect.core import genesis_subcommands
    raise typer.Exit(genesis_subcommands.cmd_research(topic))


@app.command()
def upgrade():
    """Show Pro status and how to unlock advanced features."""
    from genesis_architect.core import pro_bridge

    if pro_bridge.pro_licensed():
        typer.echo("Genesis Architect Pro: installed and licensed. All features unlocked.")
    elif pro_bridge.pro_installed():
        typer.echo("Pro is installed but not licensed.")
        typer.echo("Set GENESIS_PRO_LICENSE=<your-key>.")
        typer.echo(f"Get a license: {pro_bridge.UPGRADE_URL}")
    else:
        typer.echo("Pro is not installed. The free core covers scaffolding and")
        typer.echo("the top 3 GitHub pitfalls. Pro adds multi-source research,")
        typer.echo("pitfall ranking, video-to-pitfall, and cross-session memory.")
        typer.echo("Install: pip install genesis-architect-pro")
        typer.echo(f"Learn more: {pro_bridge.UPGRADE_URL}")


def main():
    app()


if __name__ == "__main__":
    main()
