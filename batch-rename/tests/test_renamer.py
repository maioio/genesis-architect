from pathlib import Path
import pytest
from batch_rename.renamer import plan_renames
from batch_rename.sanitizer import sanitize_filename
from batch_rename.patterns import build_pattern, PatternError
from batch_rename.exceptions import PatternError


def make_paths(names: list[str]) -> list[Path]:
    return [Path("/tmp") / name for name in names]


class TestPlanRenames:
    def test_basic_search_replace(self):
        files = make_paths(["report_2024.txt", "report_2025.txt"])
        plan = plan_renames(files, search="report", replacement="summary")
        assert plan[0][1].name == "summary_2024.txt"
        assert plan[1][1].name == "summary_2025.txt"

    def test_no_match_leaves_name_unchanged(self):
        files = make_paths(["photo.jpg"])
        plan = plan_renames(files, search="xyz", replacement="abc")
        assert plan[0][1].name == "photo.jpg"

    def test_prefix(self):
        files = make_paths(["file.txt"])
        plan = plan_renames(files, search="", replacement="", prefix="new_")
        assert plan[0][1].name == "new_file.txt"

    def test_suffix(self):
        files = make_paths(["file.txt"])
        plan = plan_renames(files, search="", replacement="", suffix="_final")
        assert plan[0][1].name == "file_final.txt"

    def test_counter(self):
        files = make_paths(["a.jpg", "b.jpg", "c.jpg"])
        plan = plan_renames(files, search="", replacement="", counter_start=1)
        assert plan[0][1].name == "a_0001.jpg"
        assert plan[2][1].name == "c_0003.jpg"

    def test_double_extension_preserved(self):
        files = make_paths(["movie.en.srt"])
        plan = plan_renames(files, search="movie", replacement="film")
        assert plan[0][1].name == "film.en.srt"

    def test_regex_mode(self):
        files = make_paths(["IMG_001.jpg", "IMG_002.jpg"])
        plan = plan_renames(files, search=r"IMG_(\d+)", replacement=r"photo_\1", use_regex=True)
        assert plan[0][1].name == "photo_001.jpg"

    def test_pure_no_filesystem_side_effects(self, tmp_path):
        files = make_paths(["ghost.txt"])  # file does not exist
        plan = plan_renames(files, search="ghost", replacement="real")
        assert plan[0][1].name == "real.txt"  # planning works without files on disk


class TestSanitizer:
    def test_strips_illegal_chars(self):
        assert sanitize_filename("file:name?.txt") == "file_name_.txt"

    def test_preserves_double_extension(self):
        assert sanitize_filename("movie.en.srt") == "movie.en.srt"

    def test_strips_trailing_dots(self):
        result = sanitize_filename("file....txt")
        assert not result.startswith(".")

    def test_reserved_name_prefixed(self):
        result = sanitize_filename("CON.txt")
        assert result.startswith("_")


class TestPatterns:
    def test_user_string_escaped_by_default(self):
        p = build_pattern("(hello)")
        assert p.pattern == r"\(hello\)"

    def test_regex_mode_not_escaped(self):
        p = build_pattern(r"\d+", use_regex=True)
        assert p.pattern == r"\d+"

    def test_invalid_regex_raises_pattern_error(self):
        with pytest.raises(PatternError):
            build_pattern("(unclosed", use_regex=True)
