# Install — The 3-Step Flow

The entire onboarding. No Docker, Python infra, Node, databases, Redis, or MCP
servers to install by hand. No license, either.

```
1. Download Genesis
2. Install
3. Start working
```

## Claude Code (available now)

1. **Install:** `pip install genesis-architect-pro` (the free `genesis-architect`
   core installs automatically as a dependency).
2. **Start working:** Pro features are unconditionally available via the free
   core's pro_bridge — no key, no activation step.

Optional deps (e.g. `ffmpeg` for video transcription) auto-install on first use,
guided by one prompt — never a wall of setup steps.

## Desktop (future, Tauri)

Signed installer (.dmg / .msi / AppImage); runtime + binaries bundled inside the
app; the app opens straight to the Floating Assistant, no first-run prompt.
Auto-updates are signed, opt-in, and rollback-safe.

## Check your readiness

```python
from genesis_architect_pro import doctor_report
print(doctor_report())     # shows what's ready, what's optional, one clear action
```

The only **required** step is that the Pro package itself is installed.
Everything else is optional and never blocks. If any default-path step ever
demands manual infrastructure, that is a packaging bug — not a documented
requirement.
