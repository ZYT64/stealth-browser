"""stealth-browser: human-like, anti-fingerprint browser automation.

Built on patchright (anti-detection fork of Playwright) + a full Chromium
build. Provides natural human interaction patterns (delays, scrolling, mouse
paths, typing) and anti-fingerprint launches.

Usage (CLI):
    stealth-browser check [sannysoft]
    stealth-browser open <url> [--profile NAME] [--wait SEC] [--keep]
    stealth-browser dump <url> [--profile NAME]
    stealth-browser snapshot <url> [--profile NAME] [--out FILE]
"""
import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

from patchright.async_api import async_playwright

# Default profile directory (overridable via STEALTH_HOME env).
STEALTH_HOME = Path(Path.home() / ".stealth-browser")
PROFILE_DIR = STEALTH_HOME / "profiles"

# Full Chromium must NOT use the headless-shell UA; override with a real
# Chrome UA. patchright only patches the full Chromium build, not the
# headless shell (which leaks HeadlessChrome / missing chrome object).
REAL_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.7827.55 Safari/537.36"
)

# Injected before page scripts run. We spoof deviceMemory and the WebGL
# renderer — headless Chrome reports `null` / SwiftShader soft-render, both
# are well-known bot signals. Note: we do NOT spoof navigator.webdriver;
# patchright removes that property entirely (a property that merely exists
# is itself a marker).
STEALTH_INIT = """
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
(() => {
  const spoof = (proto) => {
    const orig = proto.getParameter;
    proto.getParameter = function(p) {
      if (p === 37445) return 'Google Inc. (AMD)';
      if (p === 37446) return 'ANGLE (AMD, AMD Radeon Graphics (RADV VEGA10) Direct3D11 vs_5_0 ps_5_0, D3D11)';
      return orig.call(this, p);
    };
  };
  try { spoof(WebGLRenderingContext.prototype); } catch(e) {}
  try { spoof(WebGL2RenderingContext.prototype); } catch(e) {}
})();
"""


# --------------------------------------------------------------------------
# Human-like interaction helpers
# --------------------------------------------------------------------------
def human_delay(a: float = 0.8, b: float = 2.5) -> None:
    """Random human delay (seconds) modelling read/think pacing."""
    time.sleep(random.uniform(a, b))


async def human_scroll(page, steps: int | None = None, pause=(0.3, 0.9)) -> None:
    """Progressive scroll with random pauses, sometimes backtracks."""
    steps = steps or random.randint(3, 6)
    for _ in range(steps):
        delta = random.randint(150, 400) * random.choice([1, 1, 1, -1])
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(*pause))
    # Occasionally scroll back a bit, as a human re-reading would.
    if random.random() < 0.3:
        await page.mouse.wheel(0, -random.randint(50, 150))


async def human_move(page, x: int | None = None, y: int | None = None) -> None:
    """Curved (ease-in-out) mouse movement with jitter."""
    sx, sy = random.randint(200, 900), random.randint(200, 600)
    tx, ty = (
        x if x is not None else random.randint(100, 1200),
        y if y is not None else random.randint(100, 700),
    )
    steps = random.randint(12, 24)
    for i in range(1, steps + 1):
        t = i / steps
        ease = t * t * (3 - 2 * t)  # smoothstep
        cx = sx + (tx - sx) * ease + random.uniform(-6, 6)
        cy = sy + (ty - sy) * ease + random.uniform(-6, 6)
        await page.mouse.move(cx, cy)
        await asyncio.sleep(random.uniform(0.008, 0.03))


async def human_type(page, selector: str, text: str) -> None:
    """Type character-by-character with random inter-key delays."""
    await page.click(selector)
    for ch in text:
        await page.keyboard.type(ch)
        await asyncio.sleep(random.uniform(0.03, 0.12))


# --------------------------------------------------------------------------
# Browser factory
# --------------------------------------------------------------------------
async def open_browser(profile_name: str = "default", headless: bool = True):
    """Launch an anti-fingerprint browser and return (playwright, browser,
    context, profile_dir). Reuses a persistent profile's storage_state so
    cookies/logins survive restarts."""
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=headless,
        channel="chromium",
        args=["--disable-blink-features=AutomationControlled"],
    )
    profile_dir = PROFILE_DIR / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    storage = profile_dir / "state.json"
    ctx = await browser.new_context(
        user_agent=REAL_UA,
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        viewport={"width": 1366, "height": 768},
        storage_state=str(storage) if storage.exists() else None,
    )
    await ctx.add_init_script(STEALTH_INIT)
    return p, browser, ctx, profile_dir


async def save_state(ctx, profile_dir: Path) -> None:
    state = await ctx.storage_state()
    (profile_dir / "state.json").write_text(json.dumps(state))


# --------------------------------------------------------------------------
# Sub-commands
# --------------------------------------------------------------------------
async def cmd_check(args) -> None:
    from .fingerprint_check import CHECKS

    p, browser, ctx, _ = await open_browser(args.profile)
    page = await ctx.new_page()
    await page.goto("about:blank")
    res = await page.evaluate(CHECKS)
    res["permissions"] = await page.evaluate(
        "navigator.permissions.query({name:'notifications'}).then(s=>s.state)"
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))

    if args.sannysoft:
        try:
            from .fingerprint_check import sannysoft_scan
            await sannysoft_scan(page)
        except Exception as e:  # pragma: no cover
            print("SANNYSOFT_FAIL:", e)

    await browser.close()
    await p.stop()


async def cmd_dump(args) -> None:
    p, browser, ctx, profile_dir = await open_browser(args.profile)
    page = await ctx.new_page()
    await page.goto(args.url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(random.randint(1500, 3500))
    await human_scroll(page)
    text = await page.evaluate("document.body ? document.body.innerText : ''")
    print(text[:20000])
    await save_state(ctx, profile_dir)
    await browser.close()
    await p.stop()


async def cmd_open(args) -> None:
    p, browser, ctx, profile_dir = await open_browser(args.profile)
    page = await ctx.new_page()
    await page.goto(args.url, wait_until="domcontentloaded", timeout=45000)
    await human_move(page)
    await human_scroll(page)
    if args.wait:
        await asyncio.sleep(args.wait)
    print(f"Title: {await page.title()}")
    print(f"URL: {page.url}")
    if args.keep:
        print("Browser kept open — Ctrl+C to exit")
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            pass
    await save_state(ctx, profile_dir)
    await browser.close()
    await p.stop()


async def cmd_snapshot(args) -> None:
    p, browser, ctx, profile_dir = await open_browser(args.profile)
    page = await ctx.new_page()
    await page.goto(args.url, wait_until="networkidle", timeout=45000)
    await human_scroll(page)
    out = args.out or str(PROFILE_DIR.parent / f"snapshot-{int(time.time())}.png")
    await page.screenshot(path=out, full_page=False)
    print(f"Screenshot saved: {out}")
    await save_state(ctx, profile_dir)
    await browser.close()
    await p.stop()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Anti-fingerprint browser CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ck = sub.add_parser("check", help="Verify anti-fingerprint profile")
    ck.add_argument("sannysoft", nargs="?", const=True)
    ck.add_argument("--profile", default="default")
    ck.add_argument("--out", default=None)

    for name, help_text in [("open", "Open a page (human-like ops)"),
                            ("dump", "Dump page text"),
                            ("snapshot", "Screenshot a page")]:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("url")
        sp.add_argument("--profile", default="default")
        sp.add_argument("--wait", type=int, default=0)
        sp.add_argument("--keep", action="store_true")
        sp.add_argument("--out", default=None)

    args = ap.parse_args()

    if args.cmd == "check":
        asyncio.run(cmd_check(args))
    elif args.cmd == "open":
        asyncio.run(cmd_open(args))
    elif args.cmd == "dump":
        asyncio.run(cmd_dump(args))
    elif args.cmd == "snapshot":
        asyncio.run(cmd_snapshot(args))


if __name__ == "__main__":
    main()
