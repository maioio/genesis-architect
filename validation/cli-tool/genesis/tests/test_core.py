# Tests from PITFALLS.md Pitfalls 1 + 2
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import tempfile
from pathlib import Path
from core import organize_files, safe_destination, get_category

def test_get_category_image():
    assert get_category(".jpg") == "images"

def test_get_category_unknown():
    assert get_category(".xyz") == "other"

def test_organize_moves_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "photo.jpg").write_text("fake image")
        (Path(tmpdir) / "doc.pdf").write_text("fake pdf")
        result = organize_files(tmpdir)
        assert Path(tmpdir, "images", "photo.jpg").exists()
        assert Path(tmpdir, "documents", "doc.pdf").exists()

def test_dry_run_does_not_move():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "photo.jpg").write_text("fake image")
        organize_files(tmpdir, dry_run=True)
        assert (Path(tmpdir) / "photo.jpg").exists()
        assert not (Path(tmpdir) / "images").exists()

# Pitfall 1: symlinks are skipped, not followed
def test_symlink_is_skipped_not_followed():
    with tempfile.TemporaryDirectory() as base:
        with tempfile.TemporaryDirectory() as outside:
            real_file = Path(outside) / "secret.txt"
            real_file.write_text("sensitive data")
            link = Path(base) / "link.txt"
            link.symlink_to(real_file)

            result = organize_files(base)
            # Symlink must appear in skipped, not moved
            assert any("link.txt" in s["file"] for s in result["skipped"])
            assert str(link) not in result["moved"]
            # Target file must NOT have been moved
            assert real_file.exists()

# Pitfall 2: duplicate filename gets counter suffix, not overwritten
def test_duplicate_filename_not_overwritten():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Pre-create destination
        images_dir = Path(tmpdir) / "images"
        images_dir.mkdir()
        existing = images_dir / "photo.jpg"
        existing.write_text("original")

        # Now organize a new photo.jpg into same dir
        new_photo = Path(tmpdir) / "photo.jpg"
        new_photo.write_text("new photo")
        organize_files(tmpdir)

        # Both must exist
        assert (images_dir / "photo.jpg").exists()
        assert (images_dir / "photo_2.jpg").exists()
        assert (images_dir / "photo.jpg").read_text() == "original"

def test_safe_destination_increments_counter():
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / "file.txt"
        dest.write_text("exists")
        result = safe_destination(dest)
        assert result.name == "file_2.txt"
