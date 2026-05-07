import json
from pathlib import Path
from .exceptions import ConfigError

DEFAULT_CONFIG_PATH = Path.home() / ".batch-rename.json"


def load_config(path: Path | None = None) -> dict:
    """Load config from path, with explicit error on miss.

    Avoids pitfall #4 (silent config failure - wrong path silently ignored).
    Always logs whether config was found.
    """
    target = path or DEFAULT_CONFIG_PATH

    if path is not None and not target.exists():
        raise ConfigError(f"Config file not found: {target}")

    if not target.exists():
        return {}

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        print(f"[config] Loaded from {target}")
        return data
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in config {target}: {e}") from e
