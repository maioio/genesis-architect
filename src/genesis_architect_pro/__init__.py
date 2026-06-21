"""Genesis Architect Pro - the intelligence layer.

Multi-source research orchestration, pitfall ranking, video-to-pitfall
extraction, cross-session memory, package-registry validation, and
recovery diagnosis. Requires a valid license and the free
genesis-architect core package.
"""

__version__ = "5.4.0"

from genesis_architect_pro.license import require_license, LicenseError

__all__ = ["require_license", "LicenseError", "__version__"]
