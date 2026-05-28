# Genesis Architect — Demo Recording Script

**Target:** 40-second GIF showing NLU + Vault + Fork Analysis in action.
**Scenario:** FastAPI task queue — lots of known Celery/Redis pitfalls in the wild.

---

## Setup (before recording)

Open a clean terminal (120 cols x 30 rows, dark theme):

```powershell
mkdir C:\demo\taskqueue
cd C:\demo\taskqueue
set PYTHONPATH=C:\Users\User\.claude\skills\genesis-architect\src
```

---

## Recording tool

**Terminalizer** (already installed):

```bash
terminalizer record demo --config terminalizer.yml
```

**terminalizer.yml** — create this file first:

```yaml
command: cmd
cwd: C:\demo\taskqueue
cols: 100
rows: 28
frameDelay: auto
maxIdleTime: 500
quality: 100
theme:
  background: "#0d0f14"
  foreground: "#e8eaf0"
  cursor: "#7c6af7"
  black: "#0d0f14"
  blue: "#4fc3f7"
  green: "#64ffda"
  magenta: "#7c6af7"
```

---

## The Script (type exactly this)

### Step 1 - Start genesis

```
genesis init "a FastAPI task queue with Celery and Redis"
```

What appears:
```
Genesis Architect - researching: a FastAPI task queue with Celery and Redis

Phase 1: Scanning GitHub repositories...
  celery/celery (24312 stars)
  tiangolo/fastapi (73841 stars)
  encode/starlette (9821 stars)
  ... and 12 more

Phase 2: Mining GitHub Issues for pitfalls...
  Found 43 issues to analyze

Phase 3: Checking knowledge vault...
  No cache hit - generating fresh analysis

Phase 4: Choose your architecture:

  A) Minimalist - simple, small, easy to maintain
  B) Scalable   - full production setup, CI/CD, modular
  C) Quick      - fastest possible scaffold, minimal config
  D) Hybrid     - mix of minimalist core + scalable extensions
```

### Step 2 - NLU in action (type this, not "B")

```
give me the scalable approach
```

Genesis responds:
```
I'll take that as B (scalable) - correct? [y/n]
```

Type:
```
y
```

### Step 3 - Watch it build

```
Phase 5: Analyzing with LLM and generating scaffold...

Genesis Architect complete.

  Created: taskqueue/RESEARCH.md
  Created: taskqueue/PITFALLS.md

Next: cd taskqueue and review RESEARCH.md and PITFALLS.md
Run `genesis companion` to stay in active development mode.
```

### Step 4 - Show PITFALLS.md (the killer feature)

```
type taskqueue\PITFALLS.md
```

Pause 3 seconds on the output — let viewers read the real pitfalls extracted from GitHub Issues.

### Step 5 - Enter companion mode

```
genesis companion taskqueue
```

Type a question:
```
how do I handle Redis connection drops?
```

Type:
```
done
```

Stop recording.

---

## Post-processing

```bash
terminalizer render demo -o docs/assets/demo.gif --quality 90
```

Then in `docs/index.html`, replace the demo placeholder:
```html
<!-- Change this: -->
<div class="demo-placeholder"> ... </div>

<!-- To this: -->
<img src="assets/demo.gif" alt="Genesis Architect in action">
```

Target size: under 10 MB. If too large, reduce with:
```bash
terminalizer render demo -o docs/assets/demo.gif --quality 70
```

---

## Upload

```bash
mkdir docs\assets
git add docs/assets/demo.gif docs/index.html
git commit -m "feat: add demo GIF to landing page"
git push
```
