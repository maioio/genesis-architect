# Demo Recording Script

**Goal:** Show `genesis init` from start to scaffold in one clean take.
**Target length:** 2–3 minutes → GIF of ~30–60 seconds (sped up 3–4x).
**Output file:** `assets/demo.gif`

---

## Setup (before recording)

1. Open Claude Code in a clean folder:
   ```powershell
   mkdir C:\demo\log-analyzer
   cd C:\demo\log-analyzer
   claude
   ```

2. Set terminal theme for best contrast:
   - Font: Cascadia Code or Consolas, 14pt
   - Theme: Dark (black bg, white text)
   - Window size: 120 cols × 35 rows

3. Close all other windows. Full-screen the terminal.

---

## Recording tool

**ScreenToGif** (free, Windows):
- Download: https://www.screentogif.com
- Settings → Capture → Frame rate: 15 fps
- After recording: Edit → reduce frames in waiting sections → Export as GIF

---

## The Script (type exactly this)

### Step 1 — Trigger Genesis

Type slowly so each word is readable:
```
genesis init a Python CLI for analyzing log files
```
Press Enter. Pause 1 second.

### Step 2 — Phase 0 (silent, ~2 seconds)

Claude silently detects env. Nothing to type. Let it run.

### Step 3 — Phase 1 answers (Vision Alignment)

Claude asks 2–3 questions. Answer:
- Scale question → type **A** (personal/small)
- Language question → type **B** (Python)

### Step 4 — Phase 2 (Deep Discovery, ~30–60 seconds)

Claude says "Starting engineering market research…"
Let it run. This is the dramatic part — repos scrolling.
**Do not skip this.** It's the core differentiator.

### Step 5 — Phase 5 (Architecture Choice)

Claude shows the repo table + A/B options.
Type **A** (Minimalist) and press Enter.

### Step 6 — Phase 6 (Genesis Build, ~20 seconds)

Watch files being created. CI/CD being written. Tests passing.

### Step 7 — Done

Claude says "Genesis Architect complete."
Pause 3 seconds on the final output so it's readable.
Stop recording.

---

## Post-processing

1. In ScreenToGif: select frames during Phase 2 search → right-click → Speed Up (0.3x) to compress
2. Keep Phase 1 questions and Phase 6 build at normal speed
3. Export as GIF, max 15 MB (GitHub limit for inline images)
4. Save to `assets/demo.gif`

---

## Upload to GitHub

```bash
# Option A: via git (easiest)
git add assets/demo.gif
git commit -m "feat: add demo GIF"
git push

# Option B: via GitHub web
# Open any Issue → drag demo.gif → copy the raw URL → paste in README
```

The README already has the img tag pointing to:
`https://raw.githubusercontent.com/maioio/genesis-architect/main/assets/demo.gif`

Once you push the GIF to main, it appears automatically.

---

## Optional: second clip (genesis audit)

Short 30-second recording showing:
```
genesis audit ./existing-broken-project
```
Shows PITFALLS.md being generated. Good for showing the audit mode.
