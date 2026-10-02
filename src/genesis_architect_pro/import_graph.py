"""
import_graph.py - Pro compatibility wrapper.

The implementation now lives in the FREE core
(genesis_architect.core.import_graph) as part of the Free/Pro reconciliation:
the import graph is a shared base primitive that Free needs for basic
architecture analysis, and Pro extends the base engines on top of it.

This module re-exports the free-core implementation so existing Pro imports
(`from genesis_architect_pro.import_graph import ...`) keep working unchanged.
Pro adds NO behavior here - it is a pure pass-through. The old Pro implementation
is preserved in git history and will be removed only after explicit approval,
once both repos are confirmed green.

Requires: genesis-architect (free core) that ships import_graph.
"""

from genesis_architect.core.import_graph import *  # noqa: F401,F403
# Re-export names starting with "_" (used by the Pro test-suite) that `*` skips.
from genesis_architect.core.import_graph import (  # noqa: F401
    detect_language,
    build_graph,
    load_or_build,
    main,
    _collect_files,
    _extract_python_imports,
    _extract_js_ts_imports,
    _extract_go_imports,
    _extract_rust_imports,
    _resolve_module_key,
    _detect_layer,
    _find_cycles,
)
