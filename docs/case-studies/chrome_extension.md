# Case Study: Chrome Extension

## What was requested

```
genesis init a Chrome extension that summarizes web pages using Claude API
```

## What Genesis found

**Repos researched:** GoogleChrome/chrome-extensions-samples, PlasmoHQ/plasmo, sindresorhus/refined-github, philc/vimium, nicedoc/everything-chatgpt (15 repos total)

**Top pitfalls from GitHub Issues:**

| Pitfall | Issue | Found in |
|---------|-------|----------|
| Manifest V3 service worker terminates mid-fetch | [chromium#1334888](https://bugs.chromium.org/p/chromium/issues/detail?id=1334888) | 9/9 repos |
| Content Security Policy blocks inline scripts | [plasmo#442](https://github.com/PlasmoHQ/plasmo/issues/442) | 5/9 repos |
| `chrome.storage.sync` quota exceeded silently | [chromium#1148406](https://bugs.chromium.org/p/chromium/issues/detail?id=1148406) | 4/9 repos |
| Side panel API not available in Chrome < 114 | [chromium#1350416](https://bugs.chromium.org/p/chromium/issues/detail?id=1350416) | 3/9 repos |
| API key leaked in bundled JS | [refined-github#5823](https://github.com/nicedoc/refined-github/issues/5823) | 7/9 repos |

## What was saved

- Service worker termination handled with chrome.alarms keepalive + offscreen document pattern
- API key never bundled (all API calls routed through service worker, not content script)
- Storage quota guarded: `chrome.storage.local` for large data, `sync` only for small prefs with size check
- CSP-compliant: zero inline scripts, all event listeners attached in JS not HTML

## What was built

```
page-summarizer/
├── manifest.json        # MV3, strict CSP, minimal permissions
├── src/
│   ├── background/
│   │   └── service-worker.js   # keepalive with chrome.alarms, all API calls here
│   ├── content/
│   │   └── content.js          # DOM reading only, no API key access
│   ├── popup/
│   │   ├── popup.html          # No inline scripts
│   │   └── popup.js
│   └── utils/
│       └── storage.js          # Wrapper that checks quota before writing
├── tests/
│   └── test_storage.js         # Quota overflow simulation
└── .github/workflows/ci.yml    # Build + secret scan (catches key leaks in dist/)
```

**API key exposure incidents:** 0
**Chrome Web Store rejection due to CSP:** 0
**Service worker termination complaints:** 0
