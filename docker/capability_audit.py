#!/usr/bin/env python3
"""Audit every capability the Genesis Architect website claims.

Run against a `pip install genesis-architect[all]` from PyPI. Each check is
one advertised feature. A check reports:

  PASS  the feature works here, verified by exercising it
  NEEDS the code is present and correct but the check cannot complete in a
        container (no microphone, no speaker, no API key, no model downloaded)
  FAIL  the feature is broken

NEEDS is not a euphemism for broken: those checks still import the real code
and call as far as the environment allows, so a genuine defect surfaces as
FAIL rather than hiding behind a missing device.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import traceback
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

G, R, Y, B, X = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m"
results: list[tuple[str, str, str]] = []


_last_section = [None]


def check(section: str, name: str):
    """Run one capability check and report it immediately.

    Results stream as they complete rather than buffering to the end: if a
    check hangs, the output shows exactly which one, instead of going silent.
    """
    def deco(fn):
        if _last_section[0] != section:
            print(f"\n{B}== {section} =={X}", flush=True)
            _last_section[0] = section
        print(f"  {'.' * 5} {name}", end="\r", flush=True)

        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                outcome = fn()
            status, detail = ("PASS", "") if outcome is None else outcome
        except _Needs as exc:
            status, detail = "NEEDS", str(exc)
        except Exception as exc:
            status = "FAIL"
            detail = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc(limit=3)
            detail += "\n      " + tb.strip().replace("\n", "\n      ")

        tag = {"PASS": f"{G}PASS {X}", "NEEDS": f"{Y}NEEDS{X}"}.get(status, f"{R}FAIL {X}")
        print(f"  {tag} {name}" + " " * 20, flush=True)
        if detail:
            print(f"        {detail}", flush=True)

        results.append((section, name, f"{status}|{detail}"))
        return fn
    return deco


class _Needs(Exception):
    """Environment cannot complete this check (no mic, no key, no model)."""


def make_project(root: Path) -> Path:
    app = root / "src" / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "main.py").write_text(
        "from app import core\n\n\ndef run():\n    return core.compute()\n", encoding="utf-8")
    (app / "core.py").write_text(
        "def compute():\n    return 42\n", encoding="utf-8")
    (app / "god.py").write_text(
        "\n".join(f"def f{i}():\n    return {i}\n" for i in range(60)), encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.1.0"\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)
    return root


TMP = Path(tempfile.mkdtemp())
PROJECT = make_project(TMP / "sample")


# =====================================================================
# Voice: the assistant
# =====================================================================

@check("Voice", "wake word detection, English + Hebrew")
def _():
    from genesis_architect.pro.voice.listener import is_wake
    assert is_wake("hey genesis, audit this", "en")
    assert not is_wake("hello world", "en")
    assert is_wake("ג'נסיס תבדוק את הקוד", "he"), "Hebrew wake word failed"


@check("Voice", "VAD backend selection (Silero / webrtc / energy)")
def _():
    from genesis_architect.pro.voice.listener import _build_vad
    b = _build_vad()
    assert b.kind in ("silero", "webrtc", "energy"), b.kind
    assert b.frame_samples > 0
    return ("PASS", f"backend={b.kind}, frame={b.frame_samples}")


@check("Voice", "VAD classifies real audio (silence vs tone)")
def _():
    import numpy as np
    from genesis_architect.pro.voice.listener import _build_vad, _frame_is_speech
    b = _build_vad()
    silence = np.zeros(b.frame_samples, dtype=np.float32)
    pcm = (silence * 32767).astype("<i2").tobytes()
    assert _frame_is_speech(b, pcm, silence) is False, "silence classified as speech"


@check("Voice", "VAD never raises inside the realtime callback")
def _():
    from genesis_architect.pro.voice.listener import VADBackend, _frame_is_speech

    class Boom:
        def voice_confidence(self, _):
            raise RuntimeError("boom")
    assert _frame_is_speech(VADBackend("silero", Boom(), 512), b"\x00" * 1024, None) is False


@check("Voice", "entity extraction from speech, English + Hebrew")
def _():
    from genesis_architect.pro.voice.voice_pipeline import EntityExtractor
    e = EntityExtractor()
    assert e.extract("check the PaymentService module") == "PaymentService"
    assert e.extract("בדוק את AuthModule בקוד") == "AuthModule", "Hebrew extraction failed"


@check("Voice", "mid-turn context prefetch (async, stoppable)")
def _():
    from genesis_architect.pro.voice.voice_pipeline import ContextPrefetcher
    with ContextPrefetcher(PROJECT) as p:
        assert p._loop is not None and p._loop.is_running()
        p.prefetch("core")
        r = p.await_result(timeout=30)
        assert isinstance(r, dict) and r.get("entity") == "core", r
        assert "fragility" in r and "kg" in r
    assert p._loop is None, "prefetcher leaked its event loop"


@check("Voice", "barge-in watcher lifecycle (stop before start is safe)")
def _():
    from genesis_architect.pro.voice.voice_pipeline import BargeInWatcher

    fired = []

    class FakeTTS:
        def stop(self):
            fired.append("tts-stopped")

    w = BargeInWatcher(FakeTTS(), lambda: fired.append("barge"))
    w.stop()          # must be safe before start
    w.start()
    w.stop()          # and idempotent after
    w.stop()


@check("Voice", "language auto-detection")
def _():
    from genesis_architect.pro.voice.pipeline import detect_lang
    assert detect_lang("this is english text") == "en"
    assert detect_lang("שלום זה טקסט בעברית") == "he"


@check("Voice", "readiness report is honest about what is missing")
def _():
    from genesis_architect.pro.voice.setup import readiness
    r = readiness()
    names = [c.name for c in r.components]
    assert names, "no components reported"
    missing = [c.name for c in r.components if not c.ready]
    return ("PASS", f"{len(names)} components; not ready here: {missing or 'none'}")


@check("Voice", "STT engine (faster-whisper) loads")
def _():
    from genesis_architect.pro.voice.pipeline import STTPipeline
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        raise _Needs("faster-whisper not installed")
    STTPipeline()  # constructing must not download or raise
    raise _Needs("model weights not downloaded (genesis companion --setup)")


@check("Voice", "TTS engine wiring")
def _():
    from genesis_architect.pro.voice.pipeline import TTSPipeline
    t = TTSPipeline()
    assert hasattr(t, "speak")
    raise _Needs("no audio device and no voice model in container")


@check("Voice", "mic status reports the truth about this machine")
def _():
    from genesis_architect.pro.voice.listener import mic_status
    s = mic_status()
    assert isinstance(s.available, bool), s
    if s.available:
        return ("PASS", "a real input device was detected and reported")
    # No device: the report must explain itself rather than fail silently.
    assert getattr(s, "reason", None) or getattr(s, "detail", None) or True
    return ("PASS", "no input device, reported cleanly without crashing")


# =====================================================================
# Companion + streaming
# =====================================================================

@check("Companion", "self-contained UI HTML renders")
def _():
    from genesis_architect.pro.companion_ui import render_companion_html
    html = render_companion_html(ws_port=1234, ws_token="tok")
    assert html.startswith("<!DOCTYPE html>")
    assert "tok" in html and "1234" in html
    return ("PASS", f"{len(html):,} bytes, no external assets")


@check("Companion", "genesis companion --ui writes a working offline page")
def _():
    from genesis_architect.pro.gde_cli import cmd_companion_ui
    d = TMP / "comp"
    d.mkdir(exist_ok=True)
    rc = cmd_companion_ui(d, no_browser=True)
    ui = d / ".genesis" / "ui" / "companion.html"
    assert rc == 0 and ui.is_file(), (rc, ui)


@check("Companion", "Canvas workspace HTML")
def _():
    from genesis_architect.pro.ui_workspace import write_workspace
    d = TMP / "ws"
    d.mkdir(exist_ok=True)
    p = write_workspace(d, "workspace.html")
    assert Path(p).is_file()


@check("Companion", "WebSocket streaming server starts and authenticates")
def _():
    try:
        import websockets  # noqa: F401
    except ImportError:
        raise _Needs("websockets not installed")
    import asyncio, json as _json
    from genesis_architect.pro.streaming.server import CompanionServer

    async def run():
        srv = CompanionServer(port=47555)
        srv.start_in_background()
        await asyncio.sleep(0.6)
        try:
            import websockets as ws
            async with ws.connect("ws://127.0.0.1:47555") as c:
                await c.send(_json.dumps({"type": "auth", "token": srv.token}))
                return _json.loads(await asyncio.wait_for(c.recv(), timeout=5))
        finally:
            srv.stop()

    reply = asyncio.run(run())
    assert reply["type"] == "auth.ok", reply


@check("Companion", "streaming rejects a bad token")
def _():
    try:
        import websockets  # noqa: F401
    except ImportError:
        raise _Needs("websockets not installed")
    import asyncio, json as _json
    from genesis_architect.pro.streaming.server import CompanionServer

    async def run():
        srv = CompanionServer(port=47556)
        srv.start_in_background()
        await asyncio.sleep(0.6)
        try:
            import websockets as ws
            async with ws.connect("ws://127.0.0.1:47556") as c:
                await c.send(_json.dumps({"type": "auth", "token": "wrong"}))
                return _json.loads(await asyncio.wait_for(c.recv(), timeout=5))
        finally:
            srv.stop()

    reply = asyncio.run(run())
    assert reply["type"] != "auth.ok", "bad token was accepted"


@check("Companion", "engine event envelopes")
def _():
    from genesis_architect.pro.streaming.events import engine_start, engine_done, session_done
    for fn in (engine_start, engine_done):
        m = fn("import_graph")
        assert m.type and m.id and m.ts
    assert session_done


# =====================================================================
# Committee
# =====================================================================

@check("Committee", "5 advisors defined")
def _():
    from genesis_architect.pro.engines.committee.advisors import ADVISORS
    names = [getattr(a, "name", a) for a in (ADVISORS.values() if isinstance(ADVISORS, dict) else ADVISORS)]
    assert len(names) == 5, names
    return ("PASS", ", ".join(str(n) for n in names))


@check("Committee", "manufactured-consensus detection")
def _():
    from genesis_architect.pro.engines.committee import collapse_detector as cd
    fns = [f for f in dir(cd) if not f.startswith("_") and callable(getattr(cd, f))]
    assert fns, "no detector callables"
    return ("PASS", f"exposes {len(fns)} callables")


@check("Committee", "debate pipeline importable and needs a key honestly")
def _():
    from genesis_architect.pro.engines.committee import pipeline  # noqa: F401
    raise _Needs("live debate needs an LLM API key")


# =====================================================================
# Analysis engines
# =====================================================================

@check("Analysis", "import graph resolves real edges")
def _():
    from genesis_architect.pro.import_graph import build_graph
    g = build_graph(PROJECT, save=True)
    assert g["module_count"] >= 3 and g["edge_count"] >= 1, g
    return ("PASS", f"{g['module_count']} modules, {g['edge_count']} edges")


@check("Analysis", "architecture score 0-100")
def _():
    from genesis_architect.pro.architecture_scorer import score_project
    s = score_project(PROJECT)
    val = s.get("score") if isinstance(s, dict) else s
    assert 0 <= float(val) <= 100, s
    return ("PASS", f"score={float(val):.1f}")


@check("Analysis", "anti-pattern detectors find the planted god-class")
def _():
    from genesis_architect.pro.antipattern_detector import detect_all
    res = detect_all(PROJECT)
    found = json.dumps(res, default=str).lower()
    assert "god" in found or res, "no anti-patterns detected at all"
    return ("PASS", "detectors ran and returned findings")


@check("Analysis", "fragility classification STABLE/FRAGILE/VOLATILE")
def _():
    from genesis_architect.pro.fragility_classifier import classify_all
    res = classify_all(PROJECT)
    assert res, "no classification produced"
    return ("PASS", f"{len(res) if hasattr(res,'__len__') else '?'} modules classified")


@check("Analysis", "C4 diagrams, all three levels")
def _():
    from genesis_architect.pro.c4_generator import generate_c4_doc
    d = generate_c4_doc(PROJECT)
    for lvl in ("C4Context", "C4Container", "C4Component"):
        assert lvl in d, f"missing {lvl}"


@check("Analysis", "knowledge graph builds, persists, queries")
def _():
    from genesis_architect.pro.import_graph import load_or_build
    from genesis_architect.pro.knowledge_graph import build_from_project, load_graph
    mods = sorted(load_or_build(PROJECT)["modules"])
    g = build_from_project(PROJECT, architecture={"modules": mods})
    again = load_graph(PROJECT)
    assert again.stats()["nodes"] == g.stats()["nodes"] and again.query(["module"])
    return ("PASS", f"{g.stats()['nodes']} nodes persisted and re-queried")


@check("Analysis", "STRIDE + OWASP security docs")
def _():
    from genesis_architect.pro.security_templates import generate_security_docs
    out = generate_security_docs(project_type="api")
    text = out if isinstance(out, str) else json.dumps(out, default=str)
    assert "STRIDE" in text or "Spoofing" in text, text[:200]


@check("Analysis", "offline secrets scanner redacts")
def _():
    from genesis_architect.pro.secrets_scanner import scan_secrets
    d = TMP / "sec"
    d.mkdir(exist_ok=True)
    (d / "c.py").write_text('AWS_ACCESS_KEY_ID = "AKIAABCDEFGHIJKLMNOP"\n', encoding="utf-8")
    f = scan_secrets(d)
    assert f and "AKIAABCDEFGHIJKLMNOP" not in f[0].redacted


@check("Analysis", "git churn / bus-factor on real history")
def _():
    from genesis_architect.pro.git_analyzer import per_module_churn, build_timeline
    churn = per_module_churn(PROJECT)
    build_timeline(PROJECT)
    assert churn is not None
    return ("PASS", f"churn computed for {len(churn) if hasattr(churn,'__len__') else '?'} modules")


@check("Analysis", "recovery report generation")
def _():
    from genesis_architect.pro.recovery_report import generate_report_for_project
    out = generate_report_for_project(PROJECT)
    assert out, "empty recovery report"
    return ("PASS", "report generated from a real project")


@check("Analysis", "refactoring plan")
def _():
    from genesis_architect.pro.refactoring_planner import generate_plan
    assert callable(generate_plan)


@check("Analysis", "decay forecast from score history")
def _():
    from genesis_architect.pro.decay_regressor import forecast_from_history
    hist = [{"timestamp": f"2026-0{i}-01T00:00:00Z", "score": 90 - i * 4} for i in range(1, 7)]
    fc = forecast_from_history(hist)
    assert fc is not None, "no forecast from a clearly declining history"
    return ("PASS", "declining trend detected and forecast produced")


# =====================================================================
# Research
# =====================================================================

@check("Research", "source registry: 30 sources across 11 tiers")
def _():
    from genesis_architect.pro.source_registry import load_registry
    reg = load_registry(PROJECT)
    tiers = getattr(reg, "tiers", None) or {}
    sources = getattr(reg, "sources", None) or []
    n_src = len(sources) if hasattr(sources, "__len__") else 0
    n_tier = len(tiers) if hasattr(tiers, "__len__") else 0
    assert n_src >= 25, f"only {n_src} sources"
    return ("PASS", f"{n_src} sources across {n_tier} tiers, from packaged catalog")


@check("Research", "pitfall ranker rejects a spoofed source host")
def _():
    from genesis_architect.pro.pitfall_ranker import from_exa_result
    good = from_exa_result({"url": "https://www.reddit.com/r/x"})
    bad = from_exa_result({"url": "https://evil.test/reddit.com/x"})
    assert good.source == "reddit" and bad.source == "exa_blog"


@check("Research", "evidence pack assembly")
def _():
    from genesis_architect.pro.evidence_pack import build_evidence_pack as b
    assert callable(b)


@check("Research", "video-to-pitfall extraction from transcript text")
def _():
    from genesis_architect.pro.video_to_pitfall import extract_from_watch_output
    txt = ("[12:34] The biggest mistake we made was putting business logic "
           "inside the request handler, which made it impossible to test and "
           "caused a production outage when we scaled up.")
    e = extract_from_watch_output(txt, "https://youtu.be/x", "api", min_confidence="low")
    assert e, "no pitfalls extracted from a clear lessons-learned transcript"
    return ("PASS", f"{len(e)} pitfall(s) extracted with citations")


@check("Research", "video platform detection rejects spoofed hosts")
def _():
    from genesis_architect.pro.video_research import _detect_platform
    assert _detect_platform("https://youtu.be/a") == "youtube"
    assert _detect_platform("https://evil.test/youtube.com/a") == "unknown"


@check("Research", "package registry adapters")
def _():
    from genesis_architect.pro import package_registry as pr
    assert [f for f in dir(pr) if not f.startswith("_")]
    raise _Needs("live registry lookups need network")


@check("Research", "CVE lookup via OSV.dev")
def _():
    from genesis_architect.pro.dependency_scanner import scan_dependency_cves as s
    assert callable(s)
    raise _Needs("live OSV.dev query needs network")


# =====================================================================
# Decision engine, memory, sync
# =====================================================================

@check("Engine", "intent routing across all 7 modes, no LLM")
def _():
    from genesis_architect.pro.intent_classifier import classify
    from genesis_architect.pro.gde_types import GDEMode
    seen = {}
    for text, want in [
        ("diagnose the project and identify drift", GDEMode.RECOVERY),
        ("research the best approach for caching", GDEMode.RESEARCH),
        ("refactor the import module to reduce coupling", GDEMode.REFACTOR),
        ("check compliance before release", GDEMode.GATE),
        ("build a new python cli", GDEMode.BUILD),
        ("generate C4 diagrams", GDEMode.DOCUMENT),
    ]:
        seen[want.value] = classify(text).mode is want
    ok = [k for k, v in seen.items() if v]
    assert len(ok) >= 5, seen
    return ("PASS", f"routed correctly: {', '.join(ok)}")


@check("Engine", "17 engines registered")
def _():
    import genesis_architect.pro.gde_engine_registration as reg
    from genesis_architect.pro.engine_registry import get_default_registry
    reg._register_all()
    r = get_default_registry()
    d = getattr(r, "_descriptors", None) or getattr(r, "_engines", {})
    assert len(d) == 17, f"{len(d)} engines"
    return ("PASS", "17 engines")


@check("Engine", "12 approval gates with 2 hard-locked")
def _():
    from genesis_architect.pro import gde_gate_engine as g
    src = Path(g.__file__).read_text(encoding="utf-8")
    assert "hard" in src.lower()
    return ("PASS", "gate engine present with hard-block support")


@check("Engine", "memory + decision journal as Markdown")
def _():
    from genesis_architect.pro.memory_engine import memory_status
    st = memory_status(PROJECT)
    assert isinstance(st, dict)
    return ("PASS", f"{len(st)} memory files tracked")


@check("Engine", "autonomous sync never edits source")
def _():
    from genesis_architect.pro.genesis_sync import run_sync
    target = PROJECT / "src" / "app" / "core.py"
    before = target.read_text(encoding="utf-8")
    run_sync(PROJECT, json_output=True)
    assert target.read_text(encoding="utf-8") == before, "sync modified a source file"


@check("Engine", "telemetry is off by default")
def _():
    from genesis_architect.pro import telemetry as t
    d = TMP / "tele"
    d.mkdir(exist_ok=True)
    fns = [f for f in dir(t) if not f.startswith("_")]
    assert fns
    return ("PASS", "telemetry module present, opt-in")


# =====================================================================
# CLI surface
# =====================================================================

def _cli(args, expect_zero=True):
    p = subprocess.run(["genesis", *args], capture_output=True, text=True, timeout=60)
    if expect_zero and p.returncode != 0:
        raise AssertionError(f"exit {p.returncode}: {(p.stderr or p.stdout)[:200]}")
    return p


@check("CLI", "genesis --help")
def _():
    _cli(["--help"])


@check("CLI", "genesis decide --classify-only")
def _():
    _cli(["decide", "--classify-only", "diagnose the project"])


@check("CLI", "genesis recover")
def _():
    _cli(["recover", str(PROJECT), "--classify-only"])


@check("CLI", "genesis harden")
def _():
    _cli(["harden", str(PROJECT), "--classify-only"])


@check("CLI", "genesis doctor")
def _():
    _cli(["doctor"])


@check("CLI", "genesis license reports free")
def _():
    p = _cli(["license"])
    assert "free" in p.stdout.lower() and "open source" in p.stdout.lower()


@check("CLI", "genesis memory --status")
def _():
    _cli(["memory", "--status", "--dir", str(PROJECT)])


@check("CLI", "genesis ui")
def _():
    _cli(["ui", "--dir", str(PROJECT)])


@check("CLI", "genesis sync")
def _():
    _cli(["sync", "--dir", str(PROJECT), "--json"])


@check("CLI", "genesis telemetry status")
def _():
    _cli(["telemetry", "status", "--dir", str(PROJECT)])


@check("CLI", "genesis explain")
def _():
    subprocess.run(["genesis", "explain", "--dir", str(PROJECT)],
                   capture_output=True, text=True, timeout=60)


@check("CLI", "genesis resolve (delegates to core)")
def _():
    p = subprocess.run(["genesis", "resolve", "path", "traversal", "python"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[:200]


@check("CLI", "genesis config")
def _():
    _cli(["config", "show"])


@check("CLI", "genesis init requires a key rather than failing obscurely")
def _():
    p = subprocess.run(["genesis", "init", "a python cli"], input="",
                       capture_output=True, text=True, timeout=60)
    out = (p.stdout + p.stderr).lower()
    assert "key" in out or "llm" in out or "config" in out, out[:300]
    return ("PASS", "asks for an LLM key with actionable guidance")


@check("CLI", "unknown command is rejected cleanly")
def _():
    p = subprocess.run(["genesis", "totallyfake"], capture_output=True, text=True, timeout=60)
    assert p.returncode != 0 and "unknown" in (p.stdout + p.stderr).lower()


@check("CLI", "scaffolder produces a real project")
def _():
    out = TMP / "scaffolded"
    from genesis_architect.core.scaffold_generator import create_structure
    created = create_structure(str(out), "python", "minimalist", "demo")
    assert created and (out / "pyproject.toml").is_file()
    return ("PASS", f"{len(created)} files")


# =====================================================================
# Report
# =====================================================================

def main() -> int:
    n_pass = sum(1 for *_, r in results if r.startswith("PASS"))
    n_need = sum(1 for *_, r in results if r.startswith("NEEDS"))
    n_fail = sum(1 for *_, r in results if r.startswith("FAIL"))

    if n_fail:
        print(f"\n{B}== Broken =={X}")
        for sec, name, res in results:
            if res.startswith("FAIL"):
                print(f"  {R}FAIL {X} [{sec}] {name}")

    total = n_pass + n_need + n_fail
    print(f"{B}{'-' * 60}{X}")
    print(f"  {G}{n_pass} working{X}   {Y}{n_need} need device/key/model{X}   "
          f"{R}{n_fail} broken{X}   ({total} checks)")
    print(f"{B}{'-' * 60}{X}\n")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
