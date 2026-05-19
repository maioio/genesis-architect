"""Reads optional config file (.podcast-dl.json) from the current directory."""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_FILE = ".podcast-dl.json"

_DEFAULTS: dict = {
    "output_dir": "downloads",
    "max_workers": 3,
    "timeout": 30,
}


def load_config(config_path: Path | None = None) -> dict:
    """Return merged config: defaults overridden by file values."""
    cfg = dict(_DEFAULTS)
    path = config_path or Path(CONFIG_FILE)
    if path.exists():
        try:
            file_cfg = json.loads(path.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in file_cfg.items() if k in _DEFAULTS})
            log.debug("Loaded config from %s", path)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read config %s: %s - using defaults", path, exc)
    return cfg
