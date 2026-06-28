# Product Intelligence (Telemetry)

**Pro.** An anonymous, opt-in feedback loop that tells the business which engines
earn their keep — without ever touching your code, files, secrets, or identity.

## The privacy contract (binding)

1. **Default OFF.** Nothing is recorded until you explicitly consent. No
   pre-checked opt-in.
2. **Anonymous only.** A random install id, never tied to an account, machine,
   project, or path.
3. **Revocable** at any time.
4. **You can see exactly what is stored** (`describe_payload`).
5. With telemetry off, the product is **fully functional**. Telemetry is never a
   gate.

## Never collected

Source code, project files, file paths, project names, secrets / API keys,
private prompts, business documents — none of it.

## Collected only with consent

Which workflow/engine/profile was used, whether a recommendation was
accepted/rejected, where users get stuck (named points), coarse step durations,
which screens go unused. All as short enum-like tokens.

## Enforced, not trusted

A sanitizer validates every event against an allow-list and **fail-closed**
drops anything that looks like a path, a secret, free text, or an unknown event
shape. Tampered install ids are discarded on load; the transparency surface never
echoes foreign event names back.

## Usage

```python
from genesis_architect_pro import (
    set_consent, record_event, describe_payload, clear_events, revoke_consent)

set_consent(True)                              # explicit opt-in
record_event("engine_used", {"engine": "recovery", "tier": "pro"})
print(describe_payload())                       # exactly what is stored
revoke_consent()                                # stop collecting
clear_events()                                  # delete local history
```

Storage is local-first (`.genesis/telemetry/events.jsonl`); collection and any
future upload are decoupled, and you can inspect or clear at any time.
