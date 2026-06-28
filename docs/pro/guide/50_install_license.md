# Install + License — The 4-Step Flow

The entire onboarding. No Docker, Python infra, Node, databases, Redis, or MCP
servers to install by hand.

```
1. Download Genesis
2. Install
3. Enter license key
4. Start working
```

## Claude Code (available now)

1. **Install:** `pip install genesis-architect-pro` (the free `genesis-architect`
   core installs automatically as a dependency).
2. **License:** `export GENESIS_PRO_LICENSE=<key>` (from your Gumroad email).
3. **Start working:** Pro features light up automatically via the free core's
   pro_bridge.

Optional deps (e.g. `ffmpeg` for video transcription) auto-install on first use,
guided by one prompt — never a wall of setup steps.

## Desktop (future, Tauri)

Signed installer (.dmg / .msi / AppImage); runtime + binaries bundled inside the
app; paste the key on first run; the app opens with the Floating Assistant.
Auto-updates are signed, opt-in, and rollback-safe.

## License activation

- Key format: an Ed25519-signed `gpro_<payload>.<sig>`.
- **Verified offline** against an embedded public key — no phone-home, no
  account, works on air-gapped machines.
- Invalid/expired key → Pro stays dark, the **free core keeps working**, with a
  clear message.

## Check your readiness

```python
from genesis_architect_pro import doctor_report
print(doctor_report())     # shows what's ready, what's optional, one clear action
```

The only **required** step is the license. Everything else is optional and never
blocks. If any default-path step ever demands manual infrastructure, that is a
packaging bug — not a documented requirement.
