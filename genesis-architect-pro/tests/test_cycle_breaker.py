"""
Cycle breaker (G-HIGH-11): choose the import to invert from graph metrics and
propose the interface extraction that removes it.
"""

import pytest

from genesis_architect_pro import import_graph
from genesis_architect_pro.antipattern_detector import AntiPattern
from genesis_architect_pro.refactoring_planner import (
    CycleCut,
    _graph_modules,
    _interface_name,
    _interface_path,
    _rule_cycle_breaker,
    choose_cycle_cut,
    generate_plan,
)


def _mod(fan_in, fan_out, imports=None):
    entry = {"fan_in": fan_in, "fan_out": fan_out}
    if imports is not None:
        entry["imports"] = imports
    return entry


def _cycle_pattern(cycle, confidence=1.0):
    nodes = cycle[:-1] if len(cycle) > 1 and cycle[0] == cycle[-1] else cycle
    return AntiPattern(
        id=f"circular-dep-{'-'.join(nodes)}",
        type="circular-dep",
        severity="CRITICAL" if len(nodes) == 2 else "HIGH",
        file=nodes[0],
        description=f"Import cycle: {' -> '.join(cycle)}.",
        metrics={"cycle_length": len(nodes), "cycle": cycle},
        affected_modules=list(nodes),
        confidence=confidence,
        basis="cycle found in import graph",
    )


# a is imported by many and imports little: the most stable member.
TWO_NODE = {
    "src/a.py": _mod(5, 1, ["src/b.py"]),
    "src/b.py": _mod(1, 3, ["src/a.py", "src/x.py", "src/y.py"]),
}


class TestChooseCycleCut:
    def test_lowest_instability_member_is_the_source(self):
        cut = choose_cycle_cut(["src/a.py", "src/b.py", "src/a.py"], TWO_NODE)
        assert cut == CycleCut(
            source="src/a.py",
            target="src/b.py",
            interface_name="IB",
            interface_path="src/b_interface.py",
            instability=0.17,
            fan_in=5,
            fan_out=1,
        )

    def test_closing_repeat_is_optional(self):
        with_repeat = choose_cycle_cut(["src/a.py", "src/b.py", "src/a.py"], TWO_NODE)
        assert choose_cycle_cut(["src/a.py", "src/b.py"], TWO_NODE) == with_repeat

    def test_three_node_cycle_cuts_the_import_of_the_successor(self):
        modules = {"a.py": _mod(1, 2), "b.py": _mod(6, 1), "c.py": _mod(1, 1)}
        cut = choose_cycle_cut(["a.py", "b.py", "c.py", "a.py"], modules)
        assert (cut.source, cut.target) == ("b.py", "c.py")

    def test_last_member_wraps_to_the_first(self):
        modules = {"a.py": _mod(1, 2), "b.py": _mod(1, 1), "c.py": _mod(9, 1)}
        cut = choose_cycle_cut(["a.py", "b.py", "c.py", "a.py"], modules)
        assert (cut.source, cut.target) == ("c.py", "a.py")

    def test_equal_instability_prefers_lower_fan_out(self):
        modules = {"a.py": _mod(2, 2), "b.py": _mod(1, 1)}
        assert choose_cycle_cut(["a.py", "b.py"], modules).source == "b.py"

    def test_equal_instability_and_fan_out_prefers_higher_fan_in(self):
        modules = {"a.py": _mod(1, 0), "b.py": _mod(3, 0)}
        assert choose_cycle_cut(["a.py", "b.py"], modules).source == "b.py"

    def test_full_tie_breaks_on_path(self):
        modules = {"a.py": _mod(1, 1), "b.py": _mod(1, 1)}
        cut = choose_cycle_cut(["b.py", "a.py", "b.py"], modules)
        assert (cut.source, cut.target) == ("a.py", "b.py")

    def test_cycle_listed_against_import_order_uses_the_real_import(self):
        # a imports c, c imports b, b imports a, but the cycle is written a, b, c.
        modules = {
            "a.py": _mod(9, 1, ["c.py"]),
            "b.py": _mod(1, 1, ["a.py"]),
            "c.py": _mod(1, 1, ["b.py"]),
        }
        cut = choose_cycle_cut(["a.py", "b.py", "c.py", "a.py"], modules)
        assert (cut.source, cut.target) == ("a.py", "c.py")

    def test_backslash_cycle_nodes_match_posix_graph_keys(self):
        cut = choose_cycle_cut(["src\\a.py", "src\\b.py"], TWO_NODE)
        assert cut is not None
        assert cut.interface_path == "src/b_interface.py"

    @pytest.mark.parametrize("cycle", [[], ["a.py"], ["a.py", "a.py"], ["a.py", "b.py", "a.py", "b.py"]])
    def test_degenerate_cycles_return_none(self, cycle):
        modules = {"a.py": _mod(1, 1), "b.py": _mod(1, 1)}
        assert choose_cycle_cut(cycle, modules) is None

    @pytest.mark.parametrize("modules", [
        {},
        {"a.py": _mod(1, 1)},                          # b missing
        {"a.py": _mod(1, 1), "b.py": {"fan_in": 1}},    # no fan_out
        {"a.py": _mod(1, 1), "b.py": _mod(True, 1)},    # bool is not a count
        {"a.py": _mod(1, 1), "b.py": _mod(-1, 1)},
        {"a.py": _mod(1, 1), "b.py": _mod("1", 1)},
        {"a.py": _mod(1, 1), "b.py": None},
    ])
    def test_incomplete_metrics_return_none(self, modules):
        assert choose_cycle_cut(["a.py", "b.py"], modules) is None


class TestInterfaceNaming:
    @pytest.mark.parametrize("path,expected", [
        ("src/auth_service.py", "IAuthService"),
        ("src/auth-service.ts", "IAuthService"),
        ("src/authService.ts", "IAuthService"),
        ("src/auth/__init__.py", "IAuth"),
        ("web/user/index.ts", "IUser"),
        ("src\\billing\\invoice.py", "IInvoice"),
    ])
    def test_interface_name(self, path, expected):
        assert _interface_name(path) == expected

    @pytest.mark.parametrize("nodes,target,expected", [
        (["src/auth/login.py", "src/auth/session.py"], "src/auth/session.py",
         "src/auth/session_interface.py"),
        (["src/auth/a.py", "src/user/b.py"], "src/user/b.py", "src/b_interface.py"),
        (["a.py", "b.py"], "b.py", "b_interface.py"),
        (["src\\a.ts", "src\\b.ts"], "src\\b.ts", "src/b_interface.ts"),
        (["src/auth/__init__.py", "src/user/__init__.py"], "src/auth/__init__.py",
         "src/auth_interface.py"),
    ])
    def test_interface_path_goes_to_the_shared_directory(self, nodes, target, expected):
        assert _interface_path(nodes, target) == expected


class TestRuleCycleBreaker:
    def test_interface_step_from_metrics(self):
        steps = _rule_cycle_breaker([_cycle_pattern(["src/a.py", "src/b.py", "src/a.py"])], 7, TWO_NODE)
        assert len(steps) == 1
        step = steps[0]
        assert step.id == 7
        assert (step.rule, step.tier, step.priority) == ("cycle-breaker", 1, "CRITICAL")
        assert (step.complexity, step.score_impact) == ("MEDIUM", 8)
        assert step.title == "Break import cycle (2 modules): cut src/a.py -> src/b.py"
        assert "instability 0.17, fan_in 5, fan_out 1" in step.why
        assert step.why.startswith("Import cycle: src/a.py -> src/b.py -> src/a.py.")
        assert [(op.type, op.path) for op in step.operations] == [
            ("CREATE", "src/b_interface.py"),
            ("MODIFY", "src/a.py"),
            ("MODIFY", "src/b.py"),
            ("MODIFY", "[composition root]"),
        ]
        create, source, target, _ = step.operations
        assert "IB as a typing.Protocol" in create.description
        assert "must not import any cycle member" in create.description
        assert "removes the src/a.py -> src/b.py edge" in source.description
        assert "structural" in target.description
        assert "lowest instability" in step.confidence_basis

    def test_typescript_wording(self):
        modules = {"web/a.ts": _mod(4, 1), "web/b.ts": _mod(1, 2)}
        step = _rule_cycle_breaker([_cycle_pattern(["web/a.ts", "web/b.ts", "web/a.ts"])], 1, modules)[0]
        assert "IB as a TypeScript interface" in step.operations[0].description

    def test_nominal_language_must_implement(self):
        modules = {"src/A.java": _mod(4, 1), "src/B.java": _mod(1, 2)}
        step = _rule_cycle_breaker([_cycle_pattern(["src/A.java", "src/B.java", "src/A.java"])], 1, modules)[0]
        assert "abstract interface" in step.operations[0].description
        assert step.operations[2].description == "Make src/B.java implement IB from src/B_interface.java."

    def test_confidence_inherited_from_detection(self):
        step = _rule_cycle_breaker([_cycle_pattern(["src/a.py", "src/b.py"], confidence=0.9)], 1, TWO_NODE)[0]
        assert step.confidence == 0.9

    @pytest.mark.parametrize("modules", [None, {}, {"src/a.py": _mod(5, 1)}])
    def test_falls_back_without_complete_metrics(self, modules):
        step = _rule_cycle_breaker([_cycle_pattern(["src/a.py", "src/b.py", "src/a.py"])], 1, modules)[0]
        assert step.title == "Break import cycle (2 modules)"
        assert [(op.type, op.path) for op in step.operations] == [
            ("CREATE", "src/shared_types.py"),
            ("MODIFY", "src/a.py"),
            ("MODIFY", "src/b.py"),
        ]
        assert "no import-graph metrics" in step.confidence_basis

    def test_legacy_two_argument_call_still_works(self):
        steps = _rule_cycle_breaker([_cycle_pattern(["src/a.py", "src/b.py", "src/a.py"])], 1)
        assert steps[0].operations[0].path == "src/shared_types.py"

    def test_at_most_five_steps(self):
        patterns = [_cycle_pattern([f"m{i}a.py", f"m{i}b.py", f"m{i}a.py"]) for i in range(7)]
        assert len(_rule_cycle_breaker(patterns, 1, {})) == 5

    def test_step_serializes_with_the_existing_keys(self):
        step = _rule_cycle_breaker([_cycle_pattern(["src/a.py", "src/b.py"])], 1, TWO_NODE)[0]
        assert set(step.to_dict()) == {
            "id", "tier", "rule", "priority", "title", "why", "operations",
            "complexity", "score_impact", "confidence", "confidence_basis",
        }


class TestGraphModules:
    def test_empty_when_the_graph_cannot_be_built(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("graph unavailable")
        monkeypatch.setattr(import_graph, "load_or_build", boom)
        assert _graph_modules(tmp_path, None) == {}

    @pytest.mark.parametrize("graph", [None, [], {}, {"modules": []}])
    def test_empty_when_the_graph_has_no_modules_mapping(self, tmp_path, monkeypatch, graph):
        monkeypatch.setattr(import_graph, "load_or_build", lambda *a, **k: graph)
        assert _graph_modules(tmp_path, None) == {}


class TestGeneratePlan:
    def test_real_cycle_gets_an_interface_step(self, tmp_path):
        (tmp_path / "a.py").write_text("import b\n\n\ndef run():\n    return b.helper()\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("import a\n\n\ndef helper():\n    return 1\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("import a\n\na.run()\n", encoding="utf-8")

        plan = generate_plan(tmp_path, language="python", rebuild_graph=True)

        cycle_steps = [s for s in plan.steps if s.rule == "cycle-breaker"]
        assert len(cycle_steps) == 1
        step = cycle_steps[0]
        # a.py: imported by b.py and main.py, imports b.py -> I = 1/3; b.py: I = 1/2.
        assert step.title.endswith("cut a.py -> b.py")
        assert step.operations[0].path == "b_interface.py"
        assert "IB as a typing.Protocol" in step.operations[0].description
