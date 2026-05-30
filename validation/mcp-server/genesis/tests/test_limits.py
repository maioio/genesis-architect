# Tests from PITFALLS.md Pitfall 2 - result size capping
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from limits import truncate_result, MAX_ISSUES, BODY_PREVIEW_CHARS

def make_issues(n, body_len=100):
    return [{"number": i, "title": f"Issue {i}", "body": "x" * body_len, "comments": 0} for i in range(n)]

def test_caps_at_max_issues():
    issues = make_issues(100)
    result = truncate_result(issues)
    assert len(result["issues"]) == MAX_ISSUES

def test_truncated_flag_true_when_capped():
    result = truncate_result(make_issues(100))
    assert result["truncated"] is True

def test_truncated_flag_false_when_not_capped():
    result = truncate_result(make_issues(5))
    assert result["truncated"] is False

def test_body_truncated_to_preview_chars():
    issues = make_issues(1, body_len=2000)
    result = truncate_result(issues)
    assert len(result["issues"][0]["body"]) <= BODY_PREVIEW_CHARS + 20  # +20 for "... [truncated]"

def test_hard_cap_at_50_regardless_of_limit_param():
    issues = make_issues(100)
    result = truncate_result(issues, limit=200)
    assert len(result["issues"]) <= 50
