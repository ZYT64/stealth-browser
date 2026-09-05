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
import re
import sys
import time
import weakref
from pathlib import Path

from dataclasses import dataclass

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
# is itself a marker). Written as a single IIFE *expression* so it works
# both as an init script and via page.evaluate (see apply_stealth).
#
# Native toString consistency: every function the spoof injects (the WebGL
# getParameter patches, the deviceMemory/userAgentData getters, the UA-CH
# methods) is registered with a Function.prototype.toString shim so it
# stringifies to `function <name>() { [native code] }`. A patched native
# whose JS source (with the hardcoded vendor constants inside) survives a
# toString probe is the classic creepjs-style spoof tell — a spoof that
# only rewrites behaviour but not its own description is instantly found.
#
# UA-CH (Client Hints) consistency: real Chrome advertises a "Google Chrome"
# brand (plus Chromium and a greased brand) and a uaFullVersion equal to the
# UA's full version; the headless build reports only "Chromium" and a stale
# build number (e.g. 149.0.7827.0 while the UA says 149.0.7827.55). Both are
# classic bot signals checked by modern anti-bot systems (DataDome, CF, ...).
# Version placeholders are filled from REAL_UA at import time so the spoof
# can never drift from the UA we advertise.
STEALTH_INIT_TMPL = """
(() => {
  // Native-consistent toString: anti-bot libraries (creepjs and friends)
  // call Function.prototype.toString on native-looking methods to expose
  // spoofs — a patched getParameter that still shows its JS source (with
  // the hardcoded vendor constants inside) is an instant tell. Every
  // function we inject is registered with makeNative(); the shim reports
  // `function <name>() { [native code] }` for exactly those and delegates
  // to the original toString for everything else (page code unaffected).
  // Re-running this script (init script + apply_stealth) is safe: each run
  // wraps the previous toString and re-registers its own functions, and
  // delegation through the captured shim keeps earlier registrations.
  const spoofedFns = new WeakSet();
  const spoofedNames = new WeakMap();
  const nativeToString = Function.prototype.toString;
  const makeNative = (fn, name) => {
    try {
      spoofedFns.add(fn);
      spoofedNames.set(fn, name || fn.name || '');
    } catch (e) {}
    return fn;
  };
  const toStringShim = function toString() {
    if (spoofedFns.has(this)) {
      return 'function ' + (spoofedNames.get(this) || this.name || '')
        + '() { [native code] }';
    }
    return nativeToString.call(this);
  };
  Function.prototype.toString = makeNative(toStringShim, 'toString');

  Object.defineProperty(navigator, 'deviceMemory',
    {get: makeNative(() => 8, 'get deviceMemory'), configurable: true});
  const spoof = (proto) => {
    const orig = proto.getParameter;
    const patched = function getParameter(p) {
      if (p === 37445) return 'Google Inc. (AMD)';
      if (p === 37446) return 'ANGLE (AMD, AMD Radeon Graphics (RADV VEGA10) Direct3D11 vs_5_0 ps_5_0, D3D11)';
      return orig.call(this, p);
    };
    proto.getParameter = makeNative(patched, 'getParameter');
  };
  try { spoof(WebGLRenderingContext.prototype); } catch(e) {}
  try { spoof(WebGL2RenderingContext.prototype); } catch(e) {}
  // UA-CH (client hints): define unconditionally — about:blank does not
  // expose userAgentData at all, and on real pages it lives either on the
  // navigator instance or its prototype. Defining on the instance shadows
  // a prototype getter; falling back to the prototype covers the rest.
  // getHighEntropyValues/toJSON are native-registered too: plain arrows
  // here would leak the whole client-hints payload via toString.
  const uad = {
    brands: [
      {brand: 'Google Chrome', version: '__UA_MAJOR__'},
      {brand: 'Chromium', version: '__UA_MAJOR__'},
      {brand: 'Not)A;Brand', version: '24'},
    ],
    mobile: false,
    platform: 'Linux',
    getHighEntropyValues: makeNative(function getHighEntropyValues(hints) {
      return Promise.resolve({
        architecture: 'x86',
        bitness: '64',
        brands: uad.brands,
        fullVersionList: [
          {brand: 'Google Chrome', version: '__UA_FULL__'},
          {brand: 'Chromium', version: '__UA_FULL__'},
          {brand: 'Not)A;Brand', version: '24.0.0.0'},
        ],
        mobile: false,
        model: '',
        platform: 'Linux',
        platformVersion: '',
        uaFullVersion: '__UA_FULL__',
        wow64: false,
      });
    }, 'getHighEntropyValues'),
    toJSON: makeNative(function toJSON() {
      return {brands: uad.brands, mobile: false, platform: 'Linux'};
    }, 'toJSON'),
  };
  try {
    Object.defineProperty(navigator, 'userAgentData',
      {get: makeNative(() => uad, 'get userAgentData'), configurable: true});
  } catch(e) {
    try {
      Object.defineProperty(Navigator.prototype, 'userAgentData',
        {get: makeNative(() => uad, 'get userAgentData'), configurable: true});
    } catch(e2) {}
  }
})()
"""

_UA_VER = re.search(r"Chrome/(\d+\.\d+\.\d+\.\d+)", REAL_UA)
STEALTH_INIT = (
    STEALTH_INIT_TMPL
    .replace("__UA_FULL__", _UA_VER.group(1))
    .replace("__UA_MAJOR__", _UA_VER.group(1).split(".")[0])
)


async def apply_stealth(page) -> None:
    """(Re)apply the fingerprint spoof in the page's main world.

    On some patchright builds (observed: 1.61.2 on arm64) init scripts are
    evaluated in an *isolated* world, so patches injected via
    add_init_script never become visible to page scripts. Re-running the
    same spoof through page.evaluate (main world) guarantees the page sees
    the clean profile. Idempotent — safe to call after every navigation.
    """
    await page.evaluate(STEALTH_INIT)


# --------------------------------------------------------------------------
# Human-like interaction helpers
# --------------------------------------------------------------------------
# Remembered cursor position per page (Playwright does not expose the current
# mouse position). Lets consecutive human_move/human_click calls continue the
# path from wherever the cursor was left instead of teleporting.
_last_mouse: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _remember_mouse(page, x: float, y: float) -> None:
    try:
        _last_mouse[page] = (float(x), float(y))
    except TypeError:  # page not weakref-able — skip tracking
        pass


def _last_position(page):
    try:
        return _last_mouse.get(page)
    except TypeError:
        return None


def human_delay(a: float = 0.8, b: float = 2.5) -> None:
    """Random human delay (seconds) modelling read/think pacing."""
    time.sleep(random.uniform(a, b))


async def _curve_to(page, sx: float, sy: float, tx: float, ty: float,
                    steps: int | None = None, end_jitter: float = 6.0) -> None:
    """Move the mouse along an ease-in-out curve from (sx, sy) to (tx, ty).

    Jitter tapers to ``end_jitter`` (applied on every step, scaled down as the
    cursor approaches the target) so callers can require a precise landing —
    human_move keeps the loose ±6px finish, clicks need to land inside the
    element they aim at. Records the final position for cursor continuity.
    """
    steps = steps or random.randint(12, 24)
    for i in range(1, steps + 1):
        t = i / steps
        ease = t * t * (3 - 2 * t)  # smoothstep
        j = end_jitter * (1 - t)
        cx = sx + (tx - sx) * ease + random.uniform(-j, j)
        cy = sy + (ty - sy) * ease + random.uniform(-j, j)
        await page.mouse.move(cx, cy)
        await asyncio.sleep(random.uniform(0.008, 0.03))
    _remember_mouse(page, tx, ty)


async def human_move(page, x: int | None = None, y: int | None = None) -> None:
    """Curved (ease-in-out) mouse movement with jitter."""
    start = _last_position(page) or (random.randint(200, 900),
                                      random.randint(200, 600))
    sx, sy = start
    tx, ty = (
        x if x is not None else random.randint(100, 1200),
        y if y is not None else random.randint(100, 700),
    )
    await _curve_to(page, sx, sy, tx, ty)


async def human_click(page, selector: str | None = None, *,
                      locator=None, press=(0.04, 0.13)) -> None:
    """Human-like click: curved approach, random aim point, real press.

    A plain ``locator.click()`` teleports the cursor to the element center in
    one step — real browsers see a stream of movement events first, and
    instant jumps (or every click landing on dead center) are automation
    tells. This helper:

    1. scrolls the element into view and reads its bounding box,
    2. aims at a random point in the middle 50% of the box (humans miss
       dead center),
    3. moves the cursor there along the shared ease-in-out curve, starting
       from the *remembered* cursor position when one exists,
    4. pauses briefly, then presses and releases with a human down/up gap.

    Falls back to ``locator.click()`` when the element exposes no bounding
    box (hidden/detached), and to ``page.click(selector)`` for page objects
    without ``.locator`` (duck-typed stand-ins). Safe for repeated use:
    cursor continuity makes follow-up clicks start where the last ended.
    """
    loc = locator if locator is not None else (
        page.locator(selector) if hasattr(page, "locator") else None)
    if loc is None:  # duck-typed page without locator support
        await page.click(selector)
        return
    try:
        await loc.scroll_into_view_if_needed()
    except Exception:
        pass  # already in view / scroll not needed / not supported
    box = None
    try:
        box = await loc.bounding_box()
    except Exception:
        box = None
    if not box:
        await loc.click()
        return
    # Aim inside the element, biased away from the exact center.
    tx = box["x"] + box["width"] * random.uniform(0.25, 0.75)
    ty = box["y"] + box["height"] * random.uniform(0.25, 0.75)
    # Approach from the remembered cursor position, else somewhere nearby.
    sx, sy = _last_position(page) or (
        max(2, tx + random.randint(-300, 300)),
        max(2, ty + random.randint(-200, 200)),
    )
    await _curve_to(page, sx, sy, tx, ty, end_jitter=0)
    await asyncio.sleep(random.uniform(0.05, 0.2))  # confirm the target
    await page.mouse.down()
    await asyncio.sleep(random.uniform(*press))     # real press isn't instant
    await page.mouse.up()


# QWERTY adjacency for realistic typo simulation: a slip lands on a key
# next to the intended one, never a random letter. Only ASCII letters typo —
# a wrong digit/symbol can trip client-side validation before the correction
# lands, and non-Latin text has no keyboard geometry to slip on.
_ADJACENT_KEYS = {
    "q": "wa", "w": "qeas", "e": "wrsd", "r": "etdf", "t": "ryfg",
    "y": "tugh", "u": "yihj", "i": "uojk", "o": "ipkl", "p": "ol",
    "a": "qwsz", "s": "aedx", "d": "erfcx", "f": "rtgvc", "g": "tyhbv",
    "h": "yujnb", "j": "uikmn", "k": "iolm", "l": "opk",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn",
    "n": "bhm", "m": "njk",
}

# Per-character probability that an eligible letter is mistyped and then
# self-corrected. Keystroke-dynamics analysis (behavioural biometrics) flags
# text that was typed perfectly and never needed a correction — real people
# slip roughly every few hundred keys.
DEFAULT_MISTAKE_RATE = 0.03


def _mistake_rate(mistakes) -> float:
    """Normalise the ``mistakes`` knob.

    True -> DEFAULT_MISTAKE_RATE, False -> 0, or an explicit float
    probability in [0, 1] (anything else raises ValueError).
    """
    if mistakes is True:
        return DEFAULT_MISTAKE_RATE
    if mistakes is False:
        return 0.0
    try:
        rate = float(mistakes)
    except (TypeError, ValueError):
        raise ValueError("mistakes must be True, False, or a number in [0, 1]")
    if not 0.0 <= rate <= 1.0:
        raise ValueError("mistakes must be True, False, or a number in [0, 1]")
    return rate


async def human_type(page, selector: str, text: str, *,
                     mistakes: bool | float = True) -> None:
    """Type character-by-character with human keystroke dynamics.

    Focuses the field with a human-like click (curved cursor approach, not a
    teleport) before typing. See _human_type_text for the cadence model and
    the ``mistakes`` knob (occasional adjacent-key typos, self-corrected).
    """
    await human_click(page, selector)
    await _human_type_text(page, text, mistakes=mistakes)


async def _human_type_text(page, text: str, *,
                           mistakes: bool | float = True) -> None:
    """Type text character-by-character with human keystroke dynamics.

    Shared typing engine for human_type and human_fill_form; assumes the
    target field already has focus (human_click took care of it).

    Beyond random inter-key delays the cadence models how people actually
    type: familiar runs come out in quick bursts, a space occasionally gets
    a short "next word" pause and sentence punctuation a longer breath.
    With ``mistakes`` enabled (the default) a small share of letters lands
    on a QWERTY-adjacent key and is immediately corrected with Backspace —
    keystroke-dynamics analysis flags flawless input that never needs a
    correction, so perfect typing is itself a bot tell.

    ``mistakes``: True (default rate), False (never), or a float in [0, 1]
    as the per-character slip probability.
    """
    rate = _mistake_rate(mistakes)
    burst_left = 0
    for i, ch in enumerate(text):
        if (rate and ch.isascii() and ch.isalpha()
                and ch.lower() in _ADJACENT_KEYS
                and random.random() < rate):
            wrong = random.choice(_ADJACENT_KEYS[ch.lower()])
            await page.keyboard.type(wrong.upper() if ch.isupper() else wrong)
            await asyncio.sleep(random.uniform(0.15, 0.4))  # noticing the slip
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.keyboard.type(ch)
        if i == len(text) - 1:
            break  # nobody pauses after the last keystroke
        if burst_left > 0:
            burst_left -= 1
            await asyncio.sleep(random.uniform(0.015, 0.045))  # quick run
            continue
        if ch in " \t" and random.random() < 0.2:
            await asyncio.sleep(random.uniform(0.15, 0.45))  # next word...
        elif ch in ".!?,;:":
            await asyncio.sleep(random.uniform(0.08, 0.3))   # sentence breath
        elif random.random() < 0.15 and text[i + 1] not in " \t\n":
            burst_left = random.randint(1, 3)  # a familiar word flows out
            await asyncio.sleep(random.uniform(0.015, 0.045))
        else:
            await asyncio.sleep(random.uniform(0.03, 0.12))


async def human_fill_form(page, fields, *, clear: bool = True,
                          field_pause=(0.5, 1.8),
                          mistakes: bool | float = True) -> None:
    """Fill a sequence of form fields the way a person works through a form.

    Real form automation is a *sequence* of fields, and scripts that focus
    each input instantly and fill them with zero inter-field delay look
    nothing like a human filling a signup or contact form. ``fields`` is an
    iterable of ``(selector, text)`` pairs, filled one at a time:

    1. focus each field with a human-like click (same curved cursor approach
       as human_click — never a teleport),
    2. when ``clear`` and there is text to type, wipe existing content the
       way a keyboard user does (select-all + Backspace, not an instant
       ``fill("\u200b")``),
    3. type the text character-by-character with human keystroke dynamics
       (quick bursts, word/sentence-boundary pauses, occasional
       self-corrected typos — see _human_type_text),
    4. pause between fields like someone reading the next label — usually
       ``field_pause`` seconds, occasionally (~15%) a longer 0.8–2.2s
       "thinking" pause on top.

    Fields whose text is empty are focused but left untouched (no clear, no
    typing) — useful to move the cursor through the form without modifying
    those inputs. Intended for text inputs and textareas; not for <select>
    or checkbox/radio controls (use human_click for those).

    ``mistakes`` controls the typo engine (True -> default rate, False ->
    never, float in [0, 1] -> per-character slip probability); slips only
    affect ASCII letters and are always corrected before the fill moves on.
    """
    fields = list(fields)
    for i, (selector, text) in enumerate(fields):
        await human_click(page, selector)
        if clear and text:
            await page.keyboard.press("ControlOrMeta+a")
            await asyncio.sleep(random.uniform(0.05, 0.15))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.3))
        await _human_type_text(page, text, mistakes=mistakes)
        if i < len(fields) - 1:
            pause = random.uniform(*field_pause)
            if random.random() < 0.15:  # occasionally re-reads the next label
                pause += random.uniform(0.8, 2.2)
            await asyncio.sleep(pause)


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
    from .fingerprint_check import CHECKS, analyze_report, header_probe

    p, browser, ctx, _ = await open_browser(args.profile)
    page = await ctx.new_page()
    # A real document is required: init scripts don't run on about:blank and
    # permission states are meaningless there. example.com is a neutral,
    # dependency-free probe page; if offline we fall back to a blank doc.
    try:
        await page.goto("https://example.com/", wait_until="domcontentloaded",
                        timeout=20000)
    except Exception:
        await page.goto("about:blank")
    await apply_stealth(page)
    res = await page.evaluate(CHECKS)
    # Wire-level header capture (CDP): the HTTP Accept-Language header is
    # invisible to page JS, so it cannot come from the CHECKS payload — the
    # probe reads it off a live request for the header/JS locale cross-check
    # (httpAcceptLanguage in analyze_report).
    res.update(await header_probe(page))
    analysis = analyze_report(res)

    # Compact status table
    for name, c in analysis["checks"].items():
        print(f"  [{c['status']:4}] {name}: {c['note']}")
    s = analysis["summary"]
    print(
        f"verdict: {s['verdict']} "
        f"({s['passed']} pass, {s['warned']} warn, "
        f"{s['failed']} fail, {s['info']} info)"
    )

    # Structured report (JSON) — `--out` was previously a dead argument.
    out = args.out or str(
        PROFILE_DIR.parent / f"fingerprint-{time.strftime('%Y%m%d-%H%M%S')}.json"
    )
    report = {"profile": args.profile, "results": res, "analysis": analysis}
    Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report saved: {out}")

    if args.sannysoft:
        try:
            from .fingerprint_check import sannysoft_scan
            await sannysoft_scan(page)
        except Exception as e:  # pragma: no cover
            print("SANNYSOFT_FAIL:", e)

    await browser.close()
    await p.stop()
    # `check` is a verification command, so its exit code is usable in CI and
    # scripts: only a "flagged" verdict (at least one hard FAIL) exits 1.
    # WARNs (verdict "attention") still exit 0.
    if analysis["summary"]["verdict"] == "flagged":
        raise SystemExit(1)


async def cmd_dump(args) -> None:
    p, browser, ctx, profile_dir = await open_browser(args.profile)
    page = await ctx.new_page()
    await page.goto(args.url, wait_until="domcontentloaded", timeout=45000)
    await apply_stealth(page)
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
    await apply_stealth(page)
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
    await apply_stealth(page)
    await human_scroll(page)
    out = args.out or str(PROFILE_DIR.parent / f"snapshot-{int(time.time())}.png")
    await page.screenshot(path=out, full_page=False)
    print(f"Screenshot saved: {out}")
    await save_state(ctx, profile_dir)
    await browser.close()
    await p.stop()


# --------------------------------------------------------------------------
# Profile management
# --------------------------------------------------------------------------
@dataclass
class ProfileInfo:
    """Human-readable summary of a persisted browser profile."""
    name: str
    dir: Path
    age_seconds: float
    state_size: int | None
    n_profiles: int


def _scan_profiles(root: Path | None = None) -> list[ProfileInfo]:
    """Walk STEALTH_HOME/profiles and enumerate each profile directory.

    A profile is any sub-directory containing (or able to hold) a persisted
    ``state.json`` storage state. Directories without state yet (freshly
    created, never saved) are still reported so ``profiles list`` shows them.
    """
    root = root or PROFILE_DIR
    root.mkdir(parents=True, exist_ok=True)
    infos: list[ProfileInfo] = []
    now = time.time()
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        state = child / "state.json"
        mtime = state.stat().st_mtime if state.exists() else child.stat().st_mtime
        infos.append(
            ProfileInfo(
                name=child.name,
                dir=child,
                age_seconds=now - mtime,
                state_size=state.stat().st_size if state.exists() else None,
                n_profiles=len(sorted(root.iterdir())),
            )
        )
    return infos


def _reset_profile(name: str, root: Path | None = None) -> Path:
    """Remove a profile's persisted state.json (keep the profile dir).

    Useful to start fresh when a profile's cookies/localStorage look
    contaminated. Returns the path to the removed state file (or the
    profile dir if no state existed). Refuses to operate on an
    empty/``.``/``..`` name so we never touch a parent directory.
    """
    root = root or PROFILE_DIR
    # Refuse anything that is empty, a path separator, or could traverse
    # outside ``root`` (e.g. ``.``/``..``/``../etc``). We never operate on a
    # parent directory — that would risk wiping unrelated data.
    if not name or (Path(name).name != name):
        raise ValueError("profile name must be a non-empty, relative name")
    d = root / name
    try:
        resolved = d.resolve(strict=False)
    except OSError:
        resolved = d
    root_resolved = root.resolve(strict=False)
    if root_resolved not in resolved.parents and resolved != root_resolved:
        raise ValueError(f"profile name escapes profiles dir: {name}")
    if not d.is_dir():
        raise FileNotFoundError(f"profile not found: {name} (under {root})")
    state = d / "state.json"
    if state.exists():
        state.unlink()
        return state
    return d


def cmd_reset(args) -> None:
    """Reset (wipe stored login state for) a profile."""
    try:
        removed = _reset_profile(args.profile)
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}")
        raise SystemExit(1)
    if removed.is_file():
        print(f"Reset {args.profile}: removed {removed.name} (login state cleared)")
    else:
        print(f"Reset {args.profile}: no stored state to clear")


def cmd_profiles(args) -> None:
    """List existing persisted browser profiles and show the total count."""
    infos = _scan_profiles()
    if not infos:
        print("No profiles found (use `stealth-browser open <url> --profile NAME` to create one).")
        return
    # Show the newest first (most recently used on top).
    infos.sort(key=lambda i: i.age_seconds)
    print(f"{len(infos)} profile(s) under {PROFILE_DIR}")
    for i in infos:
        age = f"{i.age_seconds/3600:,.1f}h ago" if i.age_seconds >= 3600 else f"{i.age_seconds/60:,.1f}m ago"
        state = f"state.json {i.state_size:,}B" if i.state_size is not None else "no state yet"
        print(f"  - {i.name:<20} {age:<12} {state}")


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

    pr = sub.add_parser("profiles", help="List persisted browser profiles")

    rs = sub.add_parser("reset", help="Reset/clear a profile's stored login state")
    rs.add_argument("--profile", default="default")

    args = ap.parse_args()

    if args.cmd == "check":
        asyncio.run(cmd_check(args))
    elif args.cmd == "open":
        asyncio.run(cmd_open(args))
    elif args.cmd == "dump":
        asyncio.run(cmd_dump(args))
    elif args.cmd == "snapshot":
        asyncio.run(cmd_snapshot(args))
    elif args.cmd == "profiles":
        cmd_profiles(args)
    elif args.cmd == "reset":
        cmd_reset(args)


if __name__ == "__main__":
    main()
