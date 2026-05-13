"""Tests for core module."""
import pytest
from pathlib import Path
from src.python_cli.core import process_file


def test_process_file_returns_counts(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world\nfoo bar baz\n", encoding="utf-8")
    result = process_file(str(f.relative_to(Path.cwd())) if False else str(f))
    # Use absolute path since tmp_path is outside cwd - test the logic directly
    import os
    orig = os.getcwd()
    os.chdir(tmp_path.parent)
    try:
        result = process_file(str(f))
        assert result["lines"] == 2
        assert result["words"] == 5
    finally:
        os.chdir(orig)


def test_process_file_raises_on_missing():
    with pytest.raises(FileNotFoundError):
        process_file("nonexistent_file_xyz.txt")
