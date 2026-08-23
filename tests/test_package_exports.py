"""The `genesis_architect.pro` public API is lazy (PEP 562) — kept honest here.

That subpackage used to import all 43 of its modules eagerly to re-export
them. It now resolves names on first access, which keeps the public API
identical while removing the facade from the dependency graph.

The risk that swap introduces is silent: a name listed in `__all__` with no
entry in the lazy table, or an entry pointing at the wrong attribute, does not
fail at import — it fails later, for whoever imports that one name. The same
conversion in the Pro package got five aliased exports wrong, and this is the
shape of test that caught it. This package is published, so a miss here
reaches downstream users rather than only us.
"""

import importlib

import pytest

import genesis_architect.pro as pkg


class TestLazyExportTables:
    def test_every_all_name_resolves(self):
        """The whole point: no name in __all__ may be unreachable."""
        unresolvable = [n for n in pkg.__all__ if not hasattr(pkg, n)]
        assert unresolvable == []

    def test_all_and_lazy_table_agree(self):
        """Neither may drift ahead of the other.

        `__version__` is defined in __init__ itself rather than re-exported,
        so it is correctly absent from the lazy table. Every other public name
        is a re-export and must have an entry.
        """
        locally_defined = {"__version__"}
        assert set(pkg.__all__) - locally_defined == set(pkg._LAZY_EXPORTS)
        for name in locally_defined:
            assert name in pkg.__dict__

    def test_aliases_name_a_real_attribute(self):
        """An alias points at the name its module actually defines.

        This is what the eager version got for free and the lazy one has to
        state: `format_rules_report` is `rules_engine.format_report`, so
        looking up the exported name on the module would fail.
        """
        for exported, attribute in pkg._LAZY_ALIASES.items():
            module = importlib.import_module(pkg._LAZY_EXPORTS[exported])
            assert hasattr(module, attribute), f"{exported} -> {attribute}"
            assert getattr(pkg, exported) is getattr(module, attribute)

    def test_unknown_attribute_raises_attribute_error(self):
        """hasattr() and getattr(default) depend on this being AttributeError."""
        with pytest.raises(AttributeError):
            pkg.definitely_not_exported
        assert getattr(pkg, "definitely_not_exported", "fallback") == "fallback"

    def test_dir_includes_the_lazy_names(self):
        """dir() and tab-completion should still show the API."""
        assert set(pkg.__all__) <= set(dir(pkg))

    def test_resolution_is_cached(self):
        """Second access is a plain global lookup, not another import."""
        name = "GenesisDecisionEngine"
        pkg.__dict__.pop(name, None)
        first = getattr(pkg, name)
        assert name in pkg.__dict__
        assert getattr(pkg, name) is first

    def test_reload_does_not_serve_stale_objects(self):
        """importlib.reload() must rebind, as the eager version did.

        Reload re-executes the module body in the *existing* __dict__, so a
        name cached by __getattr__ before the reload would survive and shadow
        it permanently — the package would keep handing back the old object.
        Found by adversarial review, not by the suite.
        """
        name = "GenesisDecisionEngine"
        before = getattr(pkg, name)
        assert name in pkg.__dict__, "cache did not populate"

        importlib.reload(pkg)
        assert name not in pkg.__dict__, "stale export survived reload"
        assert getattr(pkg, name) is not None
        assert getattr(pkg, name) is before  # same module object, re-resolved

    def test_star_import_still_exposes_the_api(self):
        """`from genesis_architect.pro import *` is a documented usage.

        Star-import reads __all__ and resolves each name through __getattr__,
        so it is exercised here rather than assumed.
        """
        namespace: dict = {}
        exec("from genesis_architect.pro import *", namespace)  # noqa: S102
        for name in pkg.__all__:
            assert name in namespace, f"star-import missed {name}"


class TestFacadeStaysOutOfTheGraph:
    def test_importing_the_subpackage_does_not_pull_the_world(self):
        """The reason for the change, asserted rather than assumed.

        Checked in a subprocess because this test session has already imported
        most of the package.
        """
        import subprocess
        import sys

        code = (
            "import sys, genesis_architect.pro; "
            "loaded = [m for m in sys.modules "
            "if m.startswith('genesis_architect.pro.')]; "
            "print(len(loaded))"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        submodules_loaded = int(proc.stdout.strip())
        # Eager re-export pulled in 43 modules plus everything they imported.
        assert submodules_loaded < 10, (
            f"importing the subpackage loaded {submodules_loaded} submodules; "
            "the facade is eager again"
        )

    def test_one_name_pulls_only_its_own_module(self):
        import subprocess
        import sys

        code = (
            "import sys; "
            "from genesis_architect.pro import GenesisDecisionEngine; "
            "print('genesis_architect.pro.decision_engine' in sys.modules, "
            "'genesis_architect.pro.video_research' in sys.modules)"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        needed, unrelated = proc.stdout.split()
        assert needed == "True"
        assert unrelated == "False", "an unrelated module was imported too"
