"""Manages API keys stored in ~/.genesis/config.json."""

import json
from pathlib import Path

_CONFIG_PATH = Path.home() / ".genesis" / "config.json"


def _load() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def _save(data: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get(key: str) -> str | None:
    return _load().get(key)


def set_key(key: str, value: str) -> None:
    data = _load()
    data[key] = value
    _save(data)


def show() -> dict:
    data = _load()
    return {k: (v[:8] + "..." if v else "") for k, v in data.items()}
