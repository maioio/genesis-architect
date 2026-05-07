import json
from datetime import datetime
from pathlib import Path

LOG_FILENAME = ".rename_log.json"


def write_log(renames: list[tuple[Path, Path]], directory: Path) -> Path:
    """Write a JSON log of completed renames for undo support.

    Avoids pitfall #5 (no undo path after destructive rename).
    """
    entries = [{"from": str(src), "to": str(dst)} for src, dst in renames]
    log = {"timestamp": datetime.utcnow().isoformat(), "renames": entries}
    log_path = directory / LOG_FILENAME
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return log_path


def read_log(directory: Path) -> list[dict]:
    log_path = directory / LOG_FILENAME
    if not log_path.exists():
        raise FileNotFoundError(f"No rename log found in {directory}")
    return json.loads(log_path.read_text(encoding="utf-8"))["renames"]
