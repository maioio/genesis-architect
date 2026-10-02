# Privacy + Telemetry

See [Product Intelligence](29_product_intelligence.md) for the engine; this page
is the plain-language promise.

## The short version

- Telemetry is **OFF by default**. You are asked once; nothing is collected until
  you say yes.
- It is **anonymous** — a random install id, never your account, machine, or
  project.
- It is **revocable** at any time, and you can **see exactly what is stored**.
- With it off, **everything still works**. Telemetry is never a gate.

## Never collected

Source code · project files · file paths · project names · secrets / API keys ·
private prompts · business documents.

## Collected only with consent (anonymous)

Which workflow/engine/profile was used · accept/reject of recommendations · where
users get stuck (named points) · coarse step durations · unused screens.

## How it's enforced

A sanitizer drops anything that looks like a path, a secret, or free text, and
rejects unknown event shapes (fail-closed). This is enforced in code, not by
trust — see the [engine page](29_product_intelligence.md) for the contract.
