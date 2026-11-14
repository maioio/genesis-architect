---
title: New projects
description: What genesis init researches and writes, and what the agent-skill workflow adds on top.
---

```bash
genesis init "a Python CLI for analyzing log files"
```

Keep the description short. Long descriptions match nothing on GitHub.

## What `genesis init` does

The standalone command writes a research brief. It does not write application code.

1. **Context.** It reads the current directory for hints about the project.
2. **Research.** It searches GitHub only, for up to 15 repositories like the one you describe.
3. **Mining.** It reads issues from the top 5 matches and pulls out the failures that recur.
4. **Choice.** It shows what it found and asks you to pick an architecture direction: A Minimalist, B Scalable, C Quick or D Hybrid. In the standalone command the choice is echoed in the output; it does not change the files written.
5. **Brief.** Your configured LLM writes `RESEARCH.md` and `PITFALLS.md` into the output directory (an existing file of the same name is overwritten), and the run is noted in `.genesis/vault/index.json`. Each pitfall points at the issue it came from.

`init` needs `LLM_API_KEY` (`genesis config set LLM_API_KEY <key>`), even when `--model` points at a local model such as `ollama/llama3`. Without it, `init` stops before doing any research. Options: `--model`, `--name`, `--language`, `--output`.

## What it sends

The project description goes to GitHub search and to your configured LLM. For confidential work, point `--model` at a local model, or skip `init` and write the specification by hand.

## The full build is an agent-skill workflow

When Genesis runs as an agent skill (`SKILL.md`), the agent does more than the CLI:

- **Broader research.** GitHub repositories and issues, plus ecosystem and community search, package and security data and video metadata, to whatever extent the host agent has those tools.
- **Citation checks.** Before it moves on, the skill runs `scripts/research_validator.py --verify-issues`, which checks that each cited GitHub issue URL resolves. A dead link is replaced or dropped, not written down.
- **Pitfall checks.** `PITFALLS.md` must give every pitfall a live issue link and a mitigation file; the validator rejects entries that lack them.
- **The build.** After you confirm A, B, C or D, the agent writes the project itself, with the mitigations in place, tests, CI and `ROADMAP.md`, and runs a smoke test on the result.

These checks are steps of the skill workflow. `genesis init` does not run them. See [Research and evidence](../research-and-evidence/) for how the surfaces differ.

To get only the folder layout without the agent, run the structure generator directly:

```bash
python -m genesis_architect.core.scaffold_generator --language python --tier minimalist --name my-project --output .
```

It creates the folders and starter files (most of them empty) for the chosen language and tier, and never overwrites a file that already exists.
