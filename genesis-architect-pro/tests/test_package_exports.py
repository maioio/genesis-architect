"""The package's public API is lazy (PEP 562) — these assert it stays honest.

`genesis_architect_pro/__init__.py` used to import all 43 modules eagerly to
re-export them. It now resolves names on first access, which keeps the public
API identical while removing the package facade from the dependency graph.

The risk that swap introduces is silent: a name listed in `__all__` with no
entry in the lazy table, or an entry pointing at the wrong attribute, does not
fail at import — it fails later, for whoever imports that one name. The
conversion did in fact get five aliased exports wrong, and this is the shape
of test that caught it.
"""

import importlib

import pytest

import genesis_architect_pro as pkg


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


class TestFacadeStaysOutOfTheGraph:
    def test_importing_the_package_does_not_pull_the_world(self):
        """The reason for the change, asserted rather than assumed.

        Importing the package must not drag in the engine layer. Checked in a
        subprocess because this test session has already imported most of it.
        """
        import subprocess
        import sys

        code = (
            "import sys, genesis_architect_pro; "
            "loaded = [m for m in sys.modules "
            "if m.startswith('genesis_architect_pro.')]; "
            "print(len(loaded))"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        submodules_loaded = int(proc.stdout.strip())
        # Eager re-export pulled in 43 modules plus everything they imported.
        assert submodules_loaded < 10, (
            f"importing the package loaded {submodules_loaded} submodules; "
            "the facade is eager again"
        )

    def test_one_name_pulls_only_its_own_module(self):
        import subprocess
        import sys

        code = (
            "import sys; "
            "from genesis_architect_pro import GenesisDecisionEngine; "
            "print('genesis_architect_pro.decision_engine' in sys.modules, "
            "'genesis_architect_pro.video_research' in sys.modules)"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        needed, unrelated = proc.stdout.split()
        assert needed == "True"
        assert unrelated == "False", "an unrelated module was imported too"
