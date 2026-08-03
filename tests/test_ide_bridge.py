"""Tests for IDEBridgeServer and build_index_from_engine_results."""

from __future__ import annotations

import json
import time
import urllib.request
from unittest.mock import patch


from genesis_architect.pro.ide_bridge import IDEBridgeServer, build_index_from_engine_results


# ---------------------------------------------------------------------------
# build_index_from_engine_results
# ---------------------------------------------------------------------------

class TestBuildIndex:
    def test_empty_engine_results(self):
        index = build_index_from_engine_results({})
        assert index == {}

    def test_antipattern_detector_output(self):
        engine_results = {
            "antipattern_detector": {
                "output": {
                    "patterns": [
                        {
                            "pattern_type": "GOD_CLASS",
                            "severity": "HIGH",
                            "suggested_fix": "Split into smaller classes",
                            "affected_files": ["src/foo.py", "src/bar.py"],
                        }
                    ]
                }
            }
        }
        index = build_index_from_engine_results(engine_results)
        assert "src/foo.py" in index
        assert "src/bar.py" in index
        entry = index["src/foo.py"][0]
        assert entry[0] == 0  # file-level line number
        assert entry[1] == "GOD_CLASS"
        assert entry[2] == "HIGH"
        assert "smaller classes" in entry[3]

    def test_fragility_classifier_output(self):
        engine_results = {
            "fragility_classifier": {
                "output": {
                    "fragility_map": {
                        "src/volatile.py": "VOLATILE",
                        "src/fragile.py": "FRAGILE",
                        "src/stable.py": "STABLE",
                    }
                }
            }
        }
        index = build_index_from_engine_results(engine_results)
        assert "src/volatile.py" in index
        assert "src/fragile.py" in index
        assert "src/stable.py" not in index  # stable is not indexed
        assert index["src/volatile.py"][0][2] == "CRITICAL"
        assert index["src/fragile.py"][0][2] == "HIGH"

    def test_combined_engines(self):
        engine_results = {
            "antipattern_detector": {
                "output": {
                    "patterns": [
                        {
                            "pattern_type": "GOD_CLASS",
                            "severity": "HIGH",
                            "suggested_fix": "Split",
                            "affected_files": ["src/big.py"],
                        }
                    ]
                }
            },
            "fragility_classifier": {
                "output": {
                    "fragility_map": {"src/big.py": "VOLATILE"}
                }
            },
        }
        index = build_index_from_engine_results(engine_results)
        assert len(index["src/big.py"]) == 2

    def test_missing_patterns_key(self):
        engine_results = {"antipattern_detector": {"output": {}}}
        index = build_index_from_engine_results(engine_results)
        assert index == {}

    def test_missing_fragility_map_key(self):
        engine_results = {"fragility_classifier": {"output": {}}}
        index = build_index_from_engine_results(engine_results)
        assert index == {}

    def test_pattern_with_no_affected_files(self):
        engine_results = {
            "antipattern_detector": {
                "output": {
                    "patterns": [
                        {
                            "pattern_type": "CIRCULAR_DEPENDENCY",
                            "severity": "MEDIUM",
                            "suggested_fix": "Refactor",
                            "affected_files": [],
                        }
                    ]
                }
            }
        }
        index = build_index_from_engine_results(engine_results)
        assert index == {}


# ---------------------------------------------------------------------------
# IDEBridgeServer._match
# ---------------------------------------------------------------------------

class TestIDEBridgeMatch:
    def _make_server(self, index):
        server = IDEBridgeServer(pattern_index=index)
        return server

    def test_exact_line_match(self):
        index = {"src/app.py": [(42, "GOD_CLASS", "HIGH", "Split it")]}
        server = self._make_server(index)
        matches = server._match("src/app.py", 42)
        assert len(matches) == 1
        assert matches[0][0] == "GOD_CLASS"

    def test_line_tolerance_within_5(self):
        index = {"src/app.py": [(42, "GOD_CLASS", "HIGH", "Split it")]}
        server = self._make_server(index)
        assert len(server._match("src/app.py", 45)) == 1
        assert len(server._match("src/app.py", 47)) == 1
        assert len(server._match("src/app.py", 48)) == 0  # 48-42=6 > 5

    def test_file_level_match_any_line(self):
        index = {"src/app.py": [(0, "VOLATILE", "CRITICAL", "Fragile module")]}
        server = self._make_server(index)
        for line in [1, 50, 200]:
            matches = server._match("src/app.py", line)
            assert len(matches) == 1, f"Expected match at line {line}"

    def test_basename_fallback(self):
        index = {"app.py": [(0, "GOD_CLASS", "HIGH", "Split")]}
        server = self._make_server(index)
        matches = server._match("/full/path/to/app.py", 1)
        assert len(matches) == 1

    def test_max_2_hints_returned(self):
        index = {
            "src/app.py": [
                (0, "GOD_CLASS", "HIGH", "Split"),
                (0, "VOLATILE", "CRITICAL", "Fragile"),
                (0, "CIRCULAR", "MEDIUM", "Refactor"),
            ]
        }
        server = self._make_server(index)
        matches = server._match("src/app.py", 1)
        assert len(matches) == 2

    def test_no_match_returns_empty(self):
        index = {"src/other.py": [(0, "GOD_CLASS", "HIGH", "Split")]}
        server = self._make_server(index)
        assert server._match("src/app.py", 1) == []

    def test_update_index_hot_swap(self):
        index1 = {"src/a.py": [(0, "A", "HIGH", "fix a")]}
        index2 = {"src/b.py": [(0, "B", "MEDIUM", "fix b")]}
        server = self._make_server(index1)

        assert server._match("src/a.py", 1)
        assert not server._match("src/b.py", 1)

        server.update_index(index2, session_id="sess-2")
        assert not server._match("src/a.py", 1)
        assert server._match("src/b.py", 1)
        assert server._session_id == "sess-2"


# ---------------------------------------------------------------------------
# IDEBridgeServer HTTP — start / stop
# ---------------------------------------------------------------------------

class TestIDEBridgeHTTP:
    def _start_on_free_port(self, index):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        server = IDEBridgeServer(pattern_index=index, port=port)
        server.start()
        time.sleep(0.1)  # let thread spin up
        return server, port

    def test_start_and_stop(self):
        server, port = self._start_on_free_port({})
        server.stop()  # must not raise

    def test_double_start_is_idempotent(self):
        server, port = self._start_on_free_port({})
        server.start()  # second call should not start a new thread
        assert server._thread is not None
        server.stop()

    def test_post_event_returns_200(self):
        index = {"src/app.py": [(0, "GOD_CLASS", "HIGH", "Split")]}
        server, port = self._start_on_free_port(index)
        try:
            payload = json.dumps({"file": "src/app.py", "line": 10}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/ide-event",
                data=payload,
                method="POST",
                headers={"Content-Length": str(len(payload))},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                assert resp.status == 200
        finally:
            server.stop()

    def test_invalid_json_returns_400(self):
        server, port = self._start_on_free_port({})
        try:
            payload = b"not-json"
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/ide-event",
                data=payload,
                method="POST",
                headers={"Content-Length": str(len(payload))},
            )
            try:
                urllib.request.urlopen(req, timeout=2)
                assert False, "Should have raised HTTPError"
            except urllib.error.HTTPError as e:
                assert e.code == 400
        finally:
            server.stop()

    def test_event_emits_to_streaming(self):
        index = {"src/app.py": [(0, "GOD_CLASS", "HIGH", "Split it")]}
        server, port = self._start_on_free_port(index)

        emitted = []
        with patch(
            "genesis_architect.pro.ide_bridge.server.default_emitter"
        ) as mock_emitter:
            mock_emitter.emit = lambda msg: emitted.append(msg)

            # Re-call _handle directly (HTTP layer tested above)
            server._handle({"file": "src/app.py", "line": 1})
            assert len(emitted) >= 1

        server.stop()
