"""Tests for core module."""
import pytest
from pathlib import Path
from src.python_cli.core import process_file


def test_process_file_returns_counts(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world\nfoo bar baz\n", encoding="utf-8")
    result = process_file(str(f), base=tmp_path)
    assert result["lines"] == 2
    assert result["words"] == 5
    assert result["chars"] == len("hello world\nfoo bar baz\n")


def test_process_file_raises_on_missing():
    with pytest.raises(FileNotFoundError):
        process_file("nonexistent_file_xyz.txt")


def test_process_file_raises_on_traversal(tmp_path):
    (tmp_path / "legit.txt").write_text("ok", encoding="utf-8")
    safe_base = tmp_path / "safe"
    safe_base.mkdir()
    with pytest.raises(Exception):
        process_file(str(tmp_path / "legit.txt"), base=safe_base)
