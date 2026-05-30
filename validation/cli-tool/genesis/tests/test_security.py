# Tests from PITFALLS.md Pitfall 3 - path traversal guard
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import tempfile
from pathlib import Path
from security import get_safe_path

def test_valid_path_within_base_accepted():
    with tempfile.TemporaryDirectory() as base:
        result = get_safe_path(Path(base), base)
        assert str(result).startswith(str(Path(base).resolve()))

def test_path_traversal_raises():
    with tempfile.TemporaryDirectory() as base:
        with pytest.raises(ValueError, match="path traversal"):
            get_safe_path(Path(base), "/etc")

def test_dotdot_traversal_raises():
    with tempfile.TemporaryDirectory() as base:
        with pytest.raises(ValueError):
            get_safe_path(Path(base), os.path.join(base, "..", "..", "etc"))

def test_sibling_dir_raises():
    with tempfile.TemporaryDirectory() as base:
        sibling = str(Path(base).parent / "other_dir")
        with pytest.raises(ValueError):
            get_safe_path(Path(base), sibling)
