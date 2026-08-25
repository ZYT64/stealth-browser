# stealth-browser

**Human-like, anti-fingerprint browser automation toolkit** — built on
[patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (the
anti-detection fork of Playwright) + a full Chromium build.

Stop getting flagged by bot-detection systems. This toolkit gives you natural,
human-like interaction patterns (delays, scrolling, mouse paths, typing) plus
anti-fingerprint launches that pass real-world checks like
[bot.sannysoft.com](https://bot.sannysoft.com) (27/27 tests pass).

> ⚠️ **Ethics & compliance**
> This project exists for **legitimate, low-frequency automation** —
> data collection you're authorized to do, scraping public pages politely,
> RPA in your own accounts. It is **not** for abusing sites, evading bans on
> services you don't own, or anything that violates a target site's Terms of
> Service. Use responsibly.

---

## Why patchright instead of plain Playwright?

| Concern | Plain Playwright | patchright |
|---|---|---|
| `navigator.webdriver` | Set to `true` (instant bot signal) | **Removed entirely** (not spoofed — the attribute simply doesn't exist) |
| `navigator.permissions.query` | Returns `denied`/`prompt` inconsistently | Returns real human behavior |
| Headless shell artifacts | `HeadlessChrome` UA leaks | Patch only applies to full Chromium; UA overridden manually |
| `$cdc_` / CDP debug markers | Present | Cleared |

The key insight: **do NOT use `Object.defineProperty(navigator, 'webdriver', ...)`**
to spoof — the property *existing at all* is a marker. patchright's approach
of *removing* it entirely is what actually passes detection.

## Features

- 🚀 **Anti-fingerprint launch** — full Chromium (not headless-shell), real
  Chrome UA, `deviceMemory=8`, spoofed `AMD Radeon` WebGL renderer
- 🖱️ **Human-like interaction** — randomized delays, progressive scrolling
  with occasional backtracks, ease-in-out curved mouse paths, type character
  by character
- 💾 **Persistent profiles** — cookies/localStorage survive restarts, so you
  log in once and stay logged in
- 🔍 **Fingerprint self-check** — local JS checks + optional sannysoft remote
  scan
- 🌐 **Configurable** — locale, timezone, viewport, custom UA all exposed

## Install

```bash
# from the repo
pip install -e .

# core only (patchright)
pip install -e ".[core]"
```

## Usage

```bash
# 1. Verify the anti-fingerprint profile (local checks)
stealth-browser check

# JSON report written to a custom path (default: ~/.stealth-browser/fingerprint-*.json)
stealth-browser check --out /tmp/report.json

# 2. Verify against bot.sannysoft.com (remote scan, 27 checks)
stealth-browser check sannysoft

# 3. Open a page (human-like ops + persistent profile)
stealth-browser open <url> [--profile NAME] [--wait SEC] [--keep]

# 4. Dump a page's text (progressive scroll simulates reading)
stealth-browser dump <url> [--profile NAME]

# 5. Screenshot a page
stealth-browser snapshot <url> [--profile NAME] [--out FILE]
```

## Library API

```python
import asyncio
from stealth_browser.browser import open_browser, apply_stealth, human_scroll, human_type

async def main():
    p, browser, ctx, profile_dir = await open_browser("my-profile")
    page = await ctx.new_page()
    await page.goto("https://example.com")
    await apply_stealth(page)  # re-apply spoof in main world (see below)
    await human_scroll(page)
    await human_type(page, "input[name=q]", "hello world")
    # ... do work, then:
    await browser.close()
    await p.stop()

asyncio.run(main())
```

## Architecture

```
src/stealth_browser/
  browser.py            # anti-detect browser factory + human-like ops
  fingerprint_check.py  # local JS checks + sannysoft scan
```

## Anti-fingerprint check results (sannysoft, arm64 Raspberry Pi)

| Check | Status |
|---|---|
| `navigator.webdriver` | ❌ absent (removed, not spoofed) |
| HeadlessChrome UA → real Chrome 149 | ✅ |
| `permissions.query` → `prompt` | ✅ |
| `plugins` / `PluginArray` → 5 | ✅ |
| CDP debug port / `$cdc_` marker | ✅ cleared |
| `deviceMemory` → 8 | ✅ |
| WebGL renderer → AMD Radeon | ✅ |
| PhantomJS / Selenium artifacts | ✅ all pass |
| iframe / sandbox injection | ✅ all pass |

## Known limitations

- **Init scripts can run in an isolated world** — on some patchright builds
  (observed: 1.61.2 on arm64) `add_init_script` scripts execute in a world
  where their `navigator`/`WebGL` patches never become visible to page
  scripts. The toolkit therefore also re-applies the spoof in the page's
  **main world** via `apply_stealth()` after every navigation. The spoof is
  a single idempotent IIFE, so double application is harmless.
- WebGL spoof is pinned to `AMD`; adjust if the target validates GPU-vs-UA
  platform consistency
- `VIDEO_CODECS` shows `WARN` in headless (a real headless Chrome does the
  same — not a detection failure)
- **Interactive Turnstile (image click) is NOT auto-solved** — the toolkit
  stops and waits for a human. Bypassing CAPTCHAs is out of scope.
- Default is direct residential IP; configure a proxy pool separately if you
  need rotating IPs.

## License

MIT

---

*Built for legitimate automation. Don't be a jerk.*
