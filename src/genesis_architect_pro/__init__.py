"""Genesis Architect Pro - the intelligence layer.

Multi-source research orchestration, pitfall ranking, video-to-pitfall
extraction, cross-session memory, package-registry validation,
recovery diagnosis, and deep codebase analysis.

Requires a valid license and the free genesis-architect core package.
"""

__version__ = "6.0.0"

from genesis_architect_pro.license import require_license, LicenseError
from genesis_architect_pro.import_graph import build_graph, load_or_build
from genesis_architect_pro.architecture_scorer import score_project, score_label
from genesis_architect_pro.antipattern_detector import detect_all
from genesis_architect_pro.fragility_classifier import classify_all
from genesis_architect_pro.refactoring_planner import generate_plan
from genesis_architect_pro.c4_generator import generate_c4_doc
from genesis_architect_pro.security_templates import generate_security_docs

__all__ = [
    "require_license", "LicenseError", "__version__",
    "build_graph", "load_or_build",
    "score_project", "score_label",
    "detect_all",
    "classify_all",
    "generate_plan",
    "generate_c4_doc",
    "generate_security_docs",
]
