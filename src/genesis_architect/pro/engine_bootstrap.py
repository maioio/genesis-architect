"""Composition root — owns the fact that the engines are registered.

Registration used to have no owner. Whoever first noticed the registry was
empty triggered it: `engine_registry.get_default_registry()` imported the
registration module on first call, and `gde_knowledge_graph_adapter` imported
it again when it found its own dependency missing. Both were reaching
*upward* — a container importing the thing that fills it, and a descriptor
provider importing its sibling — which is what produced three of this
package's four import cycles.

The layering that holds instead:

    gde_types                    vocabulary; imports nothing intra-package
        ^
    engine_registry              a container, and only a container
        ^
    gde_engine_registration      descriptor providers; they import the
    gde_knowledge_graph_adapter  registry to register into it
        ^
    engine_bootstrap             this module: imports the providers, in order
        ^
    decision_engine / gde_cli    entry points; they ask for the bootstrap

Every arrow points one way. The registry can no longer reach the providers,
so the cycles cannot re-form by someone adding another lazy import — there is
now an obvious place for that code to go instead.

Ordering is explicit here rather than defensive at each site: the knowledge
graph engine `requires` antipattern_detector, so the core descriptors must be
registered first. That used to be enforced by the KG adapter importing the
registration module itself if it noticed the dependency was absent. Stating
the order once, in the only module whose job is ordering, is what makes the
convention unnecessary.
"""

from __future__ import annotations

_registered = False


def ensure_registered() -> None:
    """Make sure every production engine is in the default registry.

    Idempotent and cheap to call repeatedly — entry points call it without
    needing to know whether someone else already did.
    """
    global _registered
    if _registered:
        return
    _registered = True

    # Core descriptors first: the knowledge graph engine declares
    # `requires=["antipattern_detector"]`, and registering a descriptor whose
    # dependency is absent would make the registry fail its own validation.
    import genesis_architect.pro.gde_engine_registration  # noqa: F401

    # Additive and optional. Kept out of gde_engine_registration so the core
    # engine set stays what legacy callers expect, and so neither module has
    # to import the other.
    try:
        from genesis_architect.pro.gde_knowledge_graph_adapter import (
            register_knowledge_graph,
        )
        register_knowledge_graph()
    except Exception:  # noqa: BLE001
        pass  # graceful degradation: the knowledge graph is optional


def reset_for_tests() -> None:
    """Forget that registration ran, so a test can drive it again.

    The flag is module state, and a test that manipulates the registry
    directly needs a way to put this back rather than reaching into the
    private name.
    """
    global _registered
    _registered = False
