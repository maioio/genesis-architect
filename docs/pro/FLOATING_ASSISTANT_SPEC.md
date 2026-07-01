# Genesis Floating Assistant — Architecture & UX Specification

> **Status:** Specification (no implementation). Flagship UI subsystem for Genesis
> Architect PRO. This document is the authoritative design for the primary user
> interaction model: a system-wide Floating Assistant + Expanded Panel that hands
> off to the existing Canvas Workspace.
>
> **Design intent (one sentence):** Genesis becomes an AI engineering partner that
> lives quietly beside the user as a draggable, dockable status bubble, expands
> into a chat-first panel on demand, surfaces live engine state / approvals /
> recommendations through progressive disclosure, and opens the full Canvas only
> when deep analysis is needed — always respectful of attention and privacy.
>
> **Distribution / IP:** Pro-only. This subsystem, its spec, and its future
> implementation live exclusively in the **private** `genesis-architect-pro` repo
> (visible only to paying licensees). It is **never** shipped to the public
> free-core repo. It is the paid, alternative-tool interaction layer on top of the
> engines — the same chat partnership as regular Genesis, in Pro, with more.

## Visual reference (approved mockup)

The approved reference mockup (provided by the owner) establishes the canonical
look and confirms this spec covers every element. Key visual specifics locked from
it, in addition to the sections below:
- **Bubble default readout:** the compact bubble shows a live task label +
  **percentage + engine count** (e.g., "Researching authentication issue… · 67% ·
  3 engines running") with a slim progress bar — this is the default "at a glance"
  signal (see §6).
- **Panel left rail:** the expanded panel has a thin vertical **icon rail** (chat,
  status/engines, model, security, committee/people, settings) for switching the
  panel's active view (see component hierarchy).
- **Panel body:** "Current Progress" list of engines with per-engine % and a
  `Queued` state, a "Key Findings" block, and a **"View full details in Canvas"**
  hand-off row (see §6, §9, §10).
- **Bottom capability strip** (Smart Context · Live Status · Quick Actions ·
  Notifications · Canvas Integration · Multi-Engine View) maps 1:1 to §3/§6/§7/§8/
  §9/§10.
- **Footer principle:** *"The Floating Assistant is the everyday interface. The
  Canvas is for deep work. Genesis works in the background. You stay in control."*
  — this is the product's north star for the subsystem (see §2 quiet-vs-help, §4).

---

## 0. Where this fits

Genesis already has the brain and the hands: 13 engines, the Genesis Decision
Engine (intent → plan → execute → gate → report → approve → commit), Recovery
Intelligence, Knowledge Graph, Research/Field Intelligence, rules engine, MCP
tools, Memory + Decision Journal, Product Intelligence, and a zero-setup Canvas
(`ui_workspace.py`). **The missing layer is the primary interaction surface** —
how a human talks to all of this while they work. The Floating Assistant is that
surface.

Three nested surfaces, by depth:

| Surface | Role | Analogy |
|---------|------|---------|
| **Bubble** | Ambient status, always-on, one glanceable signal | Zoom floating controls |
| **Panel** | Chat-first cockpit: converse, see live state, approve, act | Copilot / Grammarly panel |
| **Canvas** | Deep workspace: graphs, C4, recovery maps, evidence | Full IDE view |

---

## 1. Window Architecture

### 1.1 Bubble (collapsed)
- **Form:** a small rounded squircle (56×56 default; 44 compact), the Genesis
  mark + a status ring. A one-word/zero-word state; a colored ring conveys most
  of it (see §11 status colors).
- **Always-on-top:** opt-in, default **on while a Genesis task is active**, else
  follows the OS norm (stays above normal windows, below full-screen apps and
  system modals).
- **Draggable:** grab anywhere on the bubble; uses OS-level window move.
- **Snap-to-edge:** within a snap threshold (~24px) it docks to the nearest screen
  edge and tucks to a half-hidden tab; hover/click re-reveals. Corners preferred.
- **Dockable:** an explicit "dock" mode pins it to an edge as a thin rail.
- **Transparency:** idle opacity configurable (default 100% active, dims to ~70%
  after 8s idle, restores on hover/new status).
- **Click-through mode:** when the user is in a focus app and the bubble is docked
  + idle, it becomes pointer-transparent so it never intercepts a click; a small
  always-clickable "ear" remains. Off by default; auto-enabled only in Focus mode.
- **Multi-monitor:** lives on the monitor where it was last placed; if that
  monitor disconnects, it migrates to the primary and re-snaps. Position is stored
  per-monitor-id so reconnecting restores it.
- **DPI scaling:** scales by the monitor's scale factor; re-renders crisply on
  monitor change (vector mark, no raster logo in the bubble).
- **Saved position:** persisted per monitor + per OS user; restored on startup.
- **Startup behavior:** launches collapsed and docked to last position; never
  steals focus on boot; shows a 1-line "Genesis ready" only on first run.
- **Focus behavior:** the bubble never takes keyboard focus on its own; clicking
  it to expand is the only focus-acquiring action.
- **Minimize:** "minimize" = collapse to bubble (the panel never appears in the
  taskbar as a separate window in the default config).
- **Animation:** bubble ↔ panel uses a single shared-element scale/translate
  (200–250ms, ease-out); status changes pulse the ring once (≤200ms); respects
  `prefers-reduced-motion` (cross-fade only).

### 1.2 Panel (expanded)
- Opens anchored to the bubble's edge, growing toward screen center; default
  ~380×560, resizable, capped so it stays "lightweight," never maximized.
- Chat-first: input always focused on open; conversation fills the panel; a
  compact **live-state strip** sits above the input.
- Dismiss: click-away (configurable), Esc, or the collapse affordance → animates
  back into the bubble.
- Always-on-top inherited from the bubble; can be temporarily pinned.

### 1.3 Docked mode
- Thin vertical/horizontal rail on a chosen edge showing only the status ring +
  the single most important live metric (e.g., "EXEC 3/5" or "⚠ approval").
- Click expands to panel in place.

### 1.4 Canvas (handoff target)
- Opens as its own larger window (or full-screen) — see §9. The Floating
  Assistant remains available as a bubble over/beside it.

---

## 2. Interaction Model — behavior by what the user is doing

The assistant reads **active-app class** (with consent, §3) and adapts *posture*,
not capability. Default posture is **Balanced** (§4).

| User is… | Default posture | Speaks when |
|----------|-----------------|-------------|
| Coding (editor focused, typing) | Quiet ring only | A gate it owns needs approval; a critical blocker; explicit @genesis |
| Using **Claude Code** | Companion | It can show the same GDE session live (engines, gates) without duplicating chat; offers "open Canvas" on drift |
| Using **VS Code** | Quiet→companion | Surfaces test/git/drift status in the ring; one suggestion max per idle period |
| In a **terminal** | Quiet | Watches test results / exit codes if shared; warns only on failures it can explain |
| Browsing / reading docs | Dormant | Stays a dim bubble; no proactive chat |
| Doing research (Genesis running) | Active status | Shows sources collected, stage, ETA in the ring + panel strip |
| Reviewing reports | Companion | Offers "explain this", "open in Canvas" |
| In design tools | Dormant | Never interrupts creative flow |
| In documents | Dormant | Only on explicit call |

**Quiet-vs-help rule:** Genesis interrupts (panel auto-open or toast) **only** for
(a) an approval it is blocking on, (b) a critical blocker, or (c) a completed task
the user explicitly started. Everything else changes the *bubble* only.

---

## 3. Context Awareness (transparent, privacy-safe)

Context is a set of **signals**, each independently toggleable, each shown in a
"What Genesis can see" inspector. Default = the minimum useful set; sensitive
signals are **off by default and require an explicit grant**.

| Signal | Default | Notes |
|--------|:------:|-------|
| Active app *class* (e.g., "editor", "terminal") | on | Class only, not window titles |
| Active project / repo path | on (per project) | Used to scope the session |
| Current files open | off | Names only when on; never contents |
| Git state (branch, dirty, ahead/behind) | on | Read-only |
| Terminal state (last exit code, test summary) | off | Opt-in per project |
| Test results | on if project has a runner | Pass/fail counts only |
| Clipboard | **off** | Only when the user explicitly "paste to Genesis" |
| Selected text | **off** | Only when explicitly "share selection" |
| Screenshots | **off** | Only on explicit "send a screenshot" request |
| Open reports | on | Genesis-generated only |
| Current Genesis session | on | Its own state |
| Previous decisions | on | From the Decision Journal |
| User preferences | on | Activity level, notification prefs |

**Privacy invariants (binding):**
1. Code, file contents, secrets, prompts, and project data are **never** sent off
   the machine (mirrors Product Intelligence §12 of the report).
2. Every signal is **inspectable** ("show me what you're using right now") and
   **revocable** instantly.
3. Clipboard / selection / screenshots are **pull, not push** — the user shares;
   Genesis never reaches in.
4. A persistent, glanceable indicator shows when any "elevated" signal (clipboard/
   selection/screenshot/terminal) was last used.

---

## 4. Activity Levels

Four levels; the **default is Balanced**. Switchable by chat ("be more proactive",
"stay quiet unless I ask") and learned over time (§ learning).

| Level | Speaks (panel/toast) | Stays silent | Asks approval | Warns | Auto-opens panel | Bubble-only |
|-------|----------------------|--------------|---------------|-------|------------------|-------------|
| **Quiet** | Only when asked | Always otherwise | Dangerous only | Critical only | Never | All status |
| **Balanced** (default) | Important only | Routine work | Dangerous + first-build | Warning+ | Approvals & critical | Info/suggestion |
| **Active** | Proactive guidance | Deep-focus typing | Dangerous + first-build | Warning+ | Approvals, critical, strong suggestions | Info |
| **Expert Partner** | Continuous co-pilot | Rarely | Dangerous only (trusts more) | All | Approvals, critical, opportunities | — |

**Binding across all levels:** dangerous/irreversible actions are **always** gated
for approval (consistent with the GDE gate policy) — even at Expert Partner.

---

## 5. Conversation Experience

- **Chat-first, natural language.** The input maps free text to GDE intent (the
  existing intent classifier), so "recover this project", "what's wrong here?",
  "continue from last time", "why did you choose that?", "be less active",
  "watch this folder" all work.
- **Inputs:** text, file drop, paste, code snippets (fenced, syntax-aware),
  screenshots **by request**, project-aware references ("this file", "the report").
  Voice is a documented future extension, not v1.
- **Memory-aware:** "continue from last time" resumes the persisted GDE session
  and cross-session memory; "why did you choose that?" reads the Decision Journal.
- **Meta-commands** adjust the assistant itself ("help me less", "show fewer
  alerts", "explain more") and persist as preference updates.
- **Turn shape:** every substantive answer can carry (a) a short prose reply, (b)
  optional quick actions (§7), (c) a "see details / open Canvas" affordance, and
  (d) for recommendations, an Evidence Pack link (honest confidence).

---

## 6. Live Status Display (progressive disclosure)

Three depths, never overloaded:

- **Bubble:** one signal — the status ring color + at most a 1–4 char glyph
  (e.g., "3/5", "⚠", "✓"). Nothing else.
- **Panel strip:** a compact row — current engine, stage of lifecycle, progress,
  confidence, approvals-needed badge, and a risk dot. Tap any chip to expand it.
- **Canvas:** the deep detail — full engine graph, evidence flow, decision flow,
  reports.

Configurable status fields (user chooses which appear in the panel strip): current
engine · running task · progress · confidence · warnings · sources collected · ETA
(only when reliable) · lifecycle stage · approvals needed · tests status · git
status · recovery status · research status · committee status · risk level.

**Rule:** ETA shows only when the engine can produce a trustworthy estimate; never
a fake spinner-number. Empty/degraded states are shown honestly (§11).

---

## 7. Quick Actions (contextual, not a static bar)

Actions are computed from current context + session state, max ~4 visible + an
overflow. Examples and when they appear:

| Action | Appears when |
|--------|--------------|
| Recover | A real project is detected, no recent recovery |
| Research / Search GitHub / Reddit / official docs | A question or library is in focus |
| Explain | A report/finding/selection is in view |
| Review / Fix | Drift or failing tests detected |
| Compare | Two+ options/alternatives are on the table |
| Run tests | A test runner exists + recent code change |
| Open report | A fresh report exists |
| Ask committee | A close/ambiguous decision |
| Generate docs | Mature model, stale docs |
| Create roadmap | Recovery finished |
| Continue last task | A resumable session exists |

---

## 8. Notification System

Levels (ascending intrusiveness): **silent status → info → suggestion → warning →
approval required → critical blocker**, plus **completed task / failed task**.

| Level | Surface |
|-------|---------|
| silent status | bubble ring only |
| info | bubble glyph; panel feed |
| suggestion | bubble accent; panel; (Active+) one toast |
| warning | bubble warn ring + toast |
| approval required | toast + panel auto-open (Balanced+) |
| critical blocker | persistent toast + panel auto-open, all levels |
| completed/failed task | toast if user started it; else feed |

Controls: **Focus mode** (suppress all but critical), **quiet hours**, **temporary
mute** (15m/1h/until tomorrow), **per-project** notification preferences,
**"show fewer like this"** and **"always show this"** on every notification (feeds
the learning model, §learning).

---

## 9. Canvas Integration

- **Assistant is the everyday surface; Canvas is opened only for depth.**
- **Open Canvas when:** the user asks ("show me the report/graph"), a
  recommendation needs a graph/C4/recovery-map to be understood, or a diff/plan
  exceeds what the panel can show.
- **Handoff:** the panel passes the current session id + focus (selected
  component/finding) to the Canvas; Canvas opens already scoped to that context.
- **Return:** Canvas updates stream back to the assistant (status ring, "N new
  findings"); a "return to compact" control collapses Canvas and re-focuses the
  bubble/panel.
- **What appears in Canvas:** reports, dependency/knowledge graphs, architecture
  (C4) maps, recovery plans (risk zones), research results / evidence packs — all
  the existing `ui_workspace` surfaces, expanded.

---

## 10. Multi-Engine Visualization

When several GDE engines run, the panel (and Canvas, in depth) shows the
execution graph from the existing planner/runner:

- engines **active / waiting / finished / failed** (color + state),
- **dependencies** between engines (the topo edges the registry already computes),
- **approvals blocking progress** (gate nodes),
- **evidence flow** (which sources fed which finding),
- **decision flow** (intent → plan → chosen alternative → journal entry).

Bubble shows the aggregate ("3/5 · ⚠1"); panel shows the lane view; Canvas shows
the full DAG.

---

## 11. Design Language

Inherits the **live-site system** (extracted from the production CSS) so the
assistant feels like the same product:

- **Palette (light/paper, default):** `--paper #f4f2ec`, `--ink #16140f`,
  `--ink2 #4a463d`, `--muted #7c776b`, `--line #dcd8cd`/`#cac4b5`, **accent
  `--accent #0b62f5`**. **Dark mode:** mirror to the `docs/pro.html` dark tokens
  (`--paper #0d1017`, `--head #e4ecf8`, accent blue→purple) for users on a dark OS.
- **Typography:** **Fraunces** (display/emphasis, italic accent), **Geist** (UI/
  body), **Geist Mono** (status, code, labels). Sizes per the site scale.
- **Spacing:** the site scale (9/13/14/17/18/20/24/32). No one-off values.
- **Cards:** `#fbfaf7` surface, `1px solid --line`, radius 16, layered soft
  shadows (`0 24px 48px -12px #16140f1f`). Pills radius 999.
- **Icons:** single-weight line set; the Genesis "GA" mark in the bubble.
- **Status colors:** idle = neutral ring; **info** = accent blue; **working** =
  animated accent arc; **suggestion** = accent soft; **warning** = amber
  `#f59e0b`; **critical/approval** = red `#f87171`; **success** = green `#3ecf8e`.
- **Progress:** determinate arc on the ring when progress is known; indeterminate
  shimmer only when it genuinely is unknown (never a fake %).
- **Animations:** 200–250ms shared-element transitions; one-shot pulses for status;
  honor `prefers-reduced-motion`.
- **Empty states:** plain, honest ("No analysis yet — say 'recover this project'").
- **Transparency / compact mode:** idle dim + compact 44px bubble defined in §1.

Accessibility (WCAG 2.2 AA, binding): keyboard-first (every action reachable, the
panel is a focus-trapped dialog with Esc-to-close), visible focus rings (accent,
2px offset), AA contrast on all text/controls in both themes, hit targets ≥44px,
all status conveyed by **text/shape + color** (never color alone), screen-reader
labels on the bubble ("Genesis: 3 of 5 engines running, 1 approval needed").

---

## 12. Technical Architecture (design, not code)

- **Desktop framework:** **Tauri** (Rust shell + web UI) recommended — small
  footprint, native always-on-top/transparency/multi-window, no bundled Chromium
  bloat, signed auto-update; honors the no-customer-setup promise (single signed
  installer). Alternatives weighed: Electron (heavier), native per-OS (costly).
  The web UI reuses the existing `ui_workspace` rendering.
- **Window model:** two native windows — a frameless always-on-top **bubble/panel**
  window and a separate **Canvas** window — coordinated by the shell.
- **IPC / event bus:** the Python Pro engines emit an **engine-event stream**
  (session lifecycle, engine start/finish/fail, gate raised, progress, confidence,
  evidence added). Transport: a local IPC channel (stdio/JSON-lines or a localhost
  socket) — local-only, never network. The web UI subscribes; the shell relays.
- **State management:** a single observable **AssistantState** (the §13 machine) in
  the UI, hydrated from persisted session + preferences; engine events are reduced
  into it.
- **Backend connection:** the assistant drives the **existing GDE** (`run/approve/
  commit`) — it adds no business logic; it is pure presentation + input routing.
- **Performance / memory:** idle cost near-zero (bubble is a tiny window; event
  stream is push, no polling); panel mounts lazily; Canvas mounts only on handoff.
  Target idle RAM modest; no busy loops; back-pressure on event floods.
- **Accessibility / security / privacy:** §11 + §3 invariants; the event channel is
  local and authenticated to the running user; license-gated (Pro).
- **Cross-platform:** Windows / macOS / Linux; per-OS handling of always-on-top,
  click-through, snap, multi-monitor, DPI documented as platform notes.
- **Update strategy:** Tauri signed updater (opt-in, rollback-safe) — same as the
  packaging plan; pip path remains for the headless/CLI engines.
- **Failure recovery:** if the engine stream drops, the bubble shows a "reconnect"
  state and retries with backoff; the last known state persists; the CLI keeps
  working regardless (assistant is never a gate on the engines).

---

## 13. Assistant State Machine

States: `idle` · `observing` · `thinking` · `researching` · `recovering` ·
`waiting_for_approval` · `warning` · `finished` · `failed` · `muted` · `expanded`
· `canvas_open`.

Two orthogonal axes: a **work state** (what the engines are doing) and a **surface
state** (bubble/expanded/canvas/muted). Sketch:

```
            ┌─────────── user expands ───────────┐
            ▼                                     │
 idle ⇄ observing ──task──▶ thinking ──▶ {researching | recovering | …}
   ▲          │                 │                  │
   │          │                 ▼                  ▼
 muted◀──mute─┤          waiting_for_approval   warning
   │          │            │ approve  │ deny       │ resolve
   │          │            ▼          ▼            ▼
   └──unmute──┘          (resume)   failed       finished
 surface overlay (any work state): bubble ⇄ expanded ⇄ canvas_open
```

- **Work transitions** are driven by engine events; **surface transitions** by the
  user (expand/collapse/open-canvas) or by policy (auto-open on approval/critical).
- `muted` suppresses surfacing but not work; `failed`/`finished` return to `idle`
  after acknowledgement; `waiting_for_approval` is the only state that can force a
  surface change at Balanced+.

---

## 14. First-Use Onboarding

A 4-step, skippable, chat-framed flow (never a wall of settings):

1. **Activity level** — "How active do you want Genesis to be?" → Quiet / Balanced
   (recommended, preselected) / Active. Copy notes it changes anytime by chat
   ("help me less", "be more proactive", "stay quiet unless I ask").
2. **Privacy / context permissions** — the §3 inspector with the default-minimum
   set on; elevated signals (clipboard/selection/screenshot/terminal) shown as
   explicit opt-ins.
3. **Project selection** — pick/confirm the current project to scope the session.
4. **Bubble + notifications** — default position/dock + default notification level;
   one line that all of it is changeable later in chat.

Ends with the bubble docked, Balanced, minimum context, and a single "Genesis is
ready — say hi or ask me to recover this project."

---

## 15. Deliverables Map (this document) + Scope

This spec contains: architecture (§1, §12), UX (§2–§9), UI/design language (§11),
window lifecycle (§1), state machine (§13), component hierarchy (below), event
model (§12), privacy model (§3), onboarding (§14), user flows (below), Canvas
integration (§9), technical plan (§12).

### Component hierarchy
```
AssistantShell (Tauri)
├─ BubbleWindow (frameless, always-on-top)
│  ├─ StatusRing (color/arc/glyph)
│  └─ DockRail (docked mode)
├─ PanelView (mounts on expand)
│  ├─ LiveStateStrip (chips: engine/stage/progress/confidence/approvals/risk)
│  ├─ Conversation (messages, quick actions, evidence links)
│  ├─ Composer (text/file-drop/paste/snippet/screenshot-request)
│  └─ NotificationLayer (toasts, focus/quiet controls)
├─ CanvasWindow (mounts on handoff) → reuses ui_workspace surfaces
└─ Services: EngineEventClient · AssistantStore · PreferenceStore ·
   ContextInspector · OnboardingFlow
```

### Event model (illustrative event names)
`session.started/ended` · `engine.queued/started/progress/finished/failed` ·
`gate.raised/cleared` · `approval.required/granted/denied` ·
`recommendation.ready` · `evidence.added` · `risk.changed` ·
`context.signal.used` · `preference.changed`.

### User flows (happy paths)
- **Recover:** type "recover this project" → bubble→thinking→recovering → panel
  strip shows engines → approval toast → approve → finished → "open report/Canvas".
- **Drift caught while coding:** code changes → ring turns amber ("claims may not
  hold") → (Balanced) bubble-only until idle → user clicks → panel offers
  "Check / Dismiss" → Check opens Canvas drift view.
- **Tune behavior:** "be less active" → confirms switch to Quiet → learning notes it.

### Scope
- **MVP:** Bubble + Panel (chat-first) + live-state strip + approval surfacing +
  Balanced default + onboarding step 1 + dark/light + drives existing GDE; Canvas
  = existing `ui_workspace` opened in a window. Single monitor, saved position.
- **v1:** snap/dock, click-through+Focus mode, full context inspector + all four
  activity levels + notifications (focus/quiet/mute/per-project) + multi-monitor +
  learning of preferences + multi-engine lane view.
- **Future:** voice input, richer Canvas interactivity, IDE-embedded variant,
  team/collaboration presence.

### Risks & mitigations
| Risk | Mitigation |
|------|-----------|
| Feels intrusive | Balanced default; bubble-only for non-critical; learning; one-tap mute |
| Privacy distrust | Default-minimum signals; pull-not-push; inspector; nothing leaves the machine |
| Platform quirks (always-on-top/click-through) | Tauri + documented per-OS notes; degrade gracefully |
| Event-stream overload | Push model + back-pressure + reduce-to-state |
| Scope creep | Strict MVP→v1→future gating above |
| Assistant becomes a dependency for the engines | Assistant is presentation-only; CLI/engines run without it |
```
```

---

*This is a specification only. Implementation is scoped but deferred per the
request. It reuses Genesis's existing engines, GDE, and `ui_workspace` Canvas — the
Floating Assistant adds the interaction layer, not new business logic.*
