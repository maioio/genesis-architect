import pytest
import os
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import organize_files, get_category

def test_get_category_image():
    assert get_category(".jpg") == "images"

def test_get_category_unknown():
    assert get_category(".xyz") == "other"

def test_organize_moves_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "photo.jpg").write_text("fake image")
        (Path(tmpdir) / "doc.pdf").write_text("fake pdf")
        result = organize_files(tmpdir)
        assert len(result) == 2
        assert Path(tmpdir, "images", "photo.jpg").exists()
        assert Path(tmpdir, "documents", "doc.pdf").exists()

def test_dry_run_does_not_move():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "photo.jpg").write_text("fake image")
        organize_files(tmpdir, dry_run=True)
        assert (Path(tmpdir) / "photo.jpg").exists()
        assert not (Path(tmpdir) / "images").exists()
