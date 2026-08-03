# Gumroad retirement copy

Two products to retire: `dduhm` (monthly) and `kzbpct` (yearly).

**Do this for each:** open the product, set it to **Unpublished** so no new
purchase can start, then replace the description with the text below so anyone
holding an old link still gets a clear answer instead of a dead page.

If you have any active subscribers, cancel their subscriptions from the
Customers tab first, and send them the email at the bottom. If there are none,
skip that step.

---

## Product title

```
Genesis Architect Pro (discontinued - everything is now free)
```

## Product description

```
Genesis Architect Pro no longer exists as a paid product, because everything
that was in it is now free.

As of v8.0.0, every engine that used to sit behind this paywall ships in the
open-source package under AGPL-3.0: the decision engine, the cross-source
knowledge graph, architecture scoring and anti-pattern detection, the recovery
scan and refactoring planner, C4 diagrams, STRIDE threat modelling, the
Committee engine, autonomous maintenance, and the voice Companion.

There is no licence key, no account, and nothing gated.

    pip install genesis-architect

Source and documentation:
https://github.com/maioio/genesis-architect

Why: this was open-core, and the split was costing more than it earned. The
tool is more useful to people if they can just run it, and more useful to me
if people actually use it. So it is all open now.

If you paid for this at any point, thank you. It genuinely helped.
```

## Cover / thumbnail note

If the cover image says "$9/mo" or "First 50 founders", replace it or remove
it. A stale price on a discontinued product is the one thing likely to confuse
someone who lands there from an old link.

---

## Email to existing subscribers (only if any exist)

Subject:

```
Genesis Architect Pro is now free - your subscription is cancelled
```

Body:

```
Hi,

Short version: I have made all of Genesis Architect free and open source, and
I have cancelled your subscription. You will not be charged again.

Everything you were paying for is in the free package as of v8.0.0, under
AGPL-3.0. Nothing is removed and nothing is gated:

    pip install -U genesis-architect

If you had the Pro package installed, remove it first, since it is
discontinued and its code now lives inside the main package:

    pip uninstall genesis-architect-pro
    pip install -U genesis-architect

`genesis license activate` still works and simply tells you there is nothing
to activate, so old scripts will not break.

Source: https://github.com/maioio/genesis-architect
Release notes: https://github.com/maioio/genesis-architect/releases/tag/v8.0.0

Thank you for backing this when it was a paid product. If anything breaks
after the upgrade, open an issue and I will look at it.

Maio
```

---

## Also worth doing

- **`maioio/genesis-architect-pro` repository**: archive it rather than delete
  it (Settings, scroll to the bottom, Archive this repository). Set its
  description to "Discontinued. Merged into
  https://github.com/maioio/genesis-architect as of v8.0.0 - everything is now
  free." The history is part of the project's story and archiving keeps it
  readable while making it clearly inactive.
- **PyPI**: nothing to do. `genesis-architect-pro` was never published there.
- **Signing key**: `~/.claude/skills/genesis-architect-pro-keys/` is no longer
  read by any code. Keep it until you are certain no old signed licence needs
  verifying, then delete it.
