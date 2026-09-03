"""Sanity tests for stealth-browser.

These exercise the human-like interaction helpers and the anti-fingerprint
launch. They need a working patchright install (see pyproject `core`
extra). The `open_browser` smoke test launches a real headless Chromium.

Run:
    pytest -q
"""
import asyncio
import os
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from stealth_browser.browser import (
    human_click,
    human_delay,
    human_fill_form,
    human_move,
    human_scroll,
    human_type,
)


# --------------------------------------------------------------------------
# human_delay / human_scroll / human_move / human_type (pure logic)
# --------------------------------------------------------------------------
def test_human_delay_range():
    """human_delay sleeps a random amount within [a, b]."""
    import time

    start = time.monotonic()
    human_delay(0.01, 0.05)  # tiny window for test speed
    elapsed = time.monotonic() - start
    assert 0.0 <= elapsed < 1.0


class _FakeMouse:
    def __init__(self):
        self.moves = []

    async def move(self, x, y):
        self.moves.append((x, y))

    async def wheel(self, dx, dy):
        self.moves.append(("wheel", dx, dy))


class _FakeKeyboard:
    """Records the key stream AND simulates a real text field: characters
    append at the cursor, select-all marks the whole content, Backspace
    deletes the selection (or the last character). Typo self-correction is
    probabilistic (keystroke dynamics), so tests assert on ``content`` /
    ``field_contents`` rather than the raw stream."""

    def __init__(self):
        self.typed = []
        self.presses = []
        # Unified (kind, value) stream in real order (type/press events).
        self.events = []
        self.content = ""      # simulated field content
        self.selected = False  # select-all state
        self.fields = []       # content snapshots when the page switches fields

    async def type(self, ch):
        self.typed.append(ch)
        self.events.append(("type", ch))
        self.content += ch
        self.selected = False

    async def press(self, key):
        self.presses.append(key)
        self.events.append(("press", key))
        if key == "ControlOrMeta+a":
            self.selected = True
        elif key == "Backspace":
            if self.selected:
                self.content = ""  # select-all + Backspace wipes the field
                self.selected = False
            elif self.content:
                self.content = self.content[:-1]

    @property
    def field_contents(self) -> list:
        """Final content of each field the fake page focused, in order."""
        return self.fields + [self.content]


class _FakePage:
    """Minimal stand-in for a Playwright page, exposing only what the
    human-like helpers use."""

    def __init__(self):
        self.mouse = _FakeMouse()
        self.keyboard = _FakeKeyboard()

    async def click(self, selector):
        self.clicked = selector


async def test_human_scroll_performs_steps():
    page = _FakePage()
    await human_scroll(page, steps=3, pause=(0.001, 0.001))
    wheels = [m for m in page.mouse.moves if m[0] == "wheel"]
    assert len(wheels) >= 2  # at least the 3 steps (some may be backtrack)


async def test_human_move_produces_path():
    page = _FakePage()
    await human_move(page, 100, 100)
    assert len(page.mouse.moves) >= 3  # interpolated multi-step path
    # final point should land within jitter distance (±6) of the target
    x, y = page.mouse.moves[-1]
    assert abs(x - 100) <= 7
    assert abs(y - 100) <= 7


async def test_human_type_chars():
    page = _FakePage()
    await human_type(page, "input#q", "hi")
    assert getattr(page, "clicked", None) == "input#q"
    # each character lands in the field, in order (a self-corrected typo
    # would put wrong keys in the raw stream — check the field content)
    assert page.keyboard.content == "hi"


# --------------------------------------------------------------------------
# human_fill_form (multi-field form filling)
# --------------------------------------------------------------------------
async def test_human_fill_form_types_fields_in_order():
    page = _FakePageWithLocator()
    await human_fill_form(page, [("input#name", "Neo"),
                                 ("input#email", "x@y.z")])
    # all characters end up in their fields, in order (simulated content)
    assert page.keyboard.field_contents == ["Neo", "x@y.z"]
    # ended focused on the last field (click-to-focus path ran for each)
    assert page.located == "input#email"
    assert page.mouse.downs == 2 and page.mouse.ups == 2  # one click per field


async def test_human_fill_form_clears_before_typing():
    """clear=True wipes each field the way a keyboard user does — select-all
    then Backspace — before the new text is typed, never an instant fill."""
    page = _FakePageWithLocator()
    await human_fill_form(page, [("input#name", "Neo")])
    # select-all is always the first press; everything else is Backspace
    # (the field wipe, plus possible typo self-corrections)
    assert page.keyboard.presses[0] == "ControlOrMeta+a"
    assert set(page.keyboard.presses) <= {"ControlOrMeta+a", "Backspace"}
    # clearing happened BEFORE the new text went in
    select_all = page.keyboard.events.index(("press", "ControlOrMeta+a"))
    first_type = next(i for i, (k, _) in enumerate(page.keyboard.events)
                      if k == "type")
    assert select_all < first_type
    assert page.keyboard.content == "Neo"


async def test_human_fill_form_clear_false_skips_wipe():
    page = _FakePageWithLocator()
    await human_fill_form(page, [("input#name", "Neo")], clear=False)
    assert "ControlOrMeta+a" not in page.keyboard.presses
    assert page.keyboard.content == "Neo"


async def test_human_fill_form_empty_text_leaves_field_untouched():
    """A field with empty text is focused (cursor continuity) but neither
    cleared nor typed into."""
    page = _FakePageWithLocator()
    await human_fill_form(page, [("input#name", "Neo"), ("input#note", "")])
    assert page.located == "input#note"
    # only the name field was cleared (plus possible typo corrections)
    assert page.keyboard.presses[0] == "ControlOrMeta+a"
    assert "ControlOrMeta+a" not in page.keyboard.presses[1:]
    assert page.keyboard.field_contents == ["Neo", ""]


# --------------------------------------------------------------------------
# Regression: duplicate helper definitions shadowed the intended ones
# --------------------------------------------------------------------------
# browser.py once defined human_move/human_type twice (an older version kept
# below the improved one). Python binds the *last* definition at import time,
# so the human-like click-before-type and cursor-continuity paths were dead
# code. These tests pin the intended behavior so the shadowing cannot return.
def test_no_shadowed_helper_definitions():
    """Every interaction helper must be defined exactly once in browser.py."""
    import stealth_browser.browser as browser_mod

    src = Path(browser_mod.__file__).read_text()
    for name in ("_curve_to", "human_move", "human_click", "human_type",
                 "human_scroll"):
        n = len(re.findall(r"async def %s\b" % re.escape(name), src))
        assert n == 1, (
            f"{name} defined {n} times — a later definition would silently "
            f"shadow the intended one at import time"
        )
    assert "human_click_stub" not in src, "leftover placeholder still present"


class _FakeLocator:
    """Stand-in for a Playwright locator exposing a bounding box."""

    def __init__(self, box):
        self._box = box
        self.scrolled = False

    async def scroll_into_view_if_needed(self):
        self.scrolled = True

    async def bounding_box(self):
        return self._box


class _FakeMouseFull(_FakeMouse):
    """_FakeMouse plus press/release tracking for human_click."""

    def __init__(self):
        super().__init__()
        self.downs = 0
        self.ups = 0

    async def down(self):
        self.downs += 1

    async def up(self):
        self.ups += 1


class _FakePageWithLocator:
    """Fake page that supports .locator() — the human-like click path."""

    def __init__(self, box=None):
        self.mouse = _FakeMouseFull()
        self.keyboard = _FakeKeyboard()
        self._box = box or {"x": 300, "y": 200, "width": 100, "height": 40}

    def locator(self, selector):
        self.located = selector
        # Switching to another field: snapshot the previous field's content
        # and start from a fresh empty input (a real form has one field per
        # input, each with its own content).
        kb = self.keyboard
        if kb.content or kb.events:
            kb.fields.append(kb.content)
        kb.content = ""
        kb.selected = False
        return _FakeLocator(self._box)


async def test_human_type_uses_human_click_path():
    """With locator support, typing must focus via a human-like click
    (curved cursor approach + real press), never a teleport page.click()."""
    page = _FakePageWithLocator()
    await human_type(page, "input#q", "ok")
    assert page.located == "input#q"
    assert page.mouse.moves, "expected a curved cursor approach before typing"
    assert page.mouse.downs == 1 and page.mouse.ups == 1
    assert page.keyboard.content == "ok"


async def test_human_click_lands_inside_bbox():
    """human_click must land inside the element box (aim point is a random
    point in the middle 50%, zero end jitter) and perform a real press."""
    box = {"x": 500, "y": 400, "width": 80, "height": 30}
    page = _FakePageWithLocator(box=box)
    await human_click(page, "button#go")
    x, y = page.mouse.moves[-1]
    assert box["x"] <= x <= box["x"] + box["width"]
    assert box["y"] <= y <= box["y"] + box["height"]
    assert page.mouse.downs == 1 and page.mouse.ups == 1


async def test_human_move_continues_from_last_position():
    """Consecutive human_move calls must continue the cursor path from where
    the previous one ended (continuity), not teleport from a fresh random
    start."""
    page = _FakePage()
    await human_move(page, 300, 300)
    first_call_len = len(page.mouse.moves)
    await human_move(page, 400, 400)
    x0, y0 = page.mouse.moves[first_call_len]
    # start of the second path must be near (300, 300) — the remembered end
    # of the first path (jitter budget ±6, scaled down on the first step)
    assert abs(x0 - 300) <= 8 and abs(y0 - 300) <= 8


# --------------------------------------------------------------------------
# Keystroke dynamics: bursts, boundary pauses, self-corrected typos
# --------------------------------------------------------------------------
def test_default_mistake_rate_is_small_but_nonzero():
    from stealth_browser.browser import DEFAULT_MISTAKE_RATE

    assert 0.0 < DEFAULT_MISTAKE_RATE < 0.2


async def test_human_type_mistakes_false_never_slips():
    """mistakes=False: the exact key stream, zero corrections."""
    page = _FakePage()
    text = "abcdefghijklmnopqrstuvwxyz"
    await human_type(page, "input#q", text, mistakes=False)
    assert page.keyboard.typed == list(text)
    assert "Backspace" not in page.keyboard.presses


async def test_human_type_mistakes_always_slips_adjacent():
    """mistakes=1.0: every eligible letter first lands on an adjacent key
    (case preserved) and is corrected with Backspace — the field still ends
    up with exactly the intended text."""
    from stealth_browser.browser import _ADJACENT_KEYS

    page = _FakePage()
    text = "aBcde"
    await human_type(page, "input#q", text, mistakes=1.0)
    assert page.keyboard.content == text
    ev = page.keyboard.events
    assert len(ev) == 3 * len(text)  # (type wrong, Backspace, type right) x n
    for j, ch in enumerate(text):
        wrong_ev, bs_ev, right_ev = ev[3 * j], ev[3 * j + 1], ev[3 * j + 2]
        assert wrong_ev[0] == "type" and wrong_ev[1] != ch
        assert bs_ev == ("press", "Backspace")
        assert right_ev == ("type", ch)
        wrong = wrong_ev[1]
        assert wrong.lower() in _ADJACENT_KEYS[ch.lower()]
        assert wrong.isupper() == ch.isupper()


async def test_human_type_never_slips_on_non_letters():
    """Digits, punctuation and spaces are never mistyped — a wrong digit
    could trip client-side validation before the correction lands."""
    page = _FakePage()
    await human_type(page, "input#q", "123 45.6", mistakes=1.0)
    assert page.keyboard.typed == list("123 45.6")
    assert "Backspace" not in page.keyboard.presses


async def test_human_type_rejects_invalid_mistake_rate():
    page = _FakePage()
    with pytest.raises(ValueError):
        await human_type(page, "input#q", "hi", mistakes=1.5)


async def test_human_fill_form_threads_mistakes_knob():
    page = _FakePageWithLocator()
    await human_fill_form(page, [("input#name", "abcdef")], mistakes=False)
    assert page.keyboard.typed == list("abcdef")
    assert page.keyboard.presses == ["ControlOrMeta+a", "Backspace"]


# --------------------------------------------------------------------------
# STEALTH_INIT — spoof script sanity (no browser needed)
# --------------------------------------------------------------------------
def test_stealth_init_registers_tostring_shim():
    """Spoofed natives must survive Function.prototype.toString probing.

    A patched getParameter whose JS source (with the hardcoded vendor
    constants) survives a toString call is the classic creepjs-style tell,
    so the spoof must ship a toString shim and register every injected
    function with it.
    """
    from stealth_browser.browser import STEALTH_INIT

    assert "Function.prototype.toString" in STEALTH_INIT
    assert "makeNative" in STEALTH_INIT
    assert "[native code]" in STEALTH_INIT
    # every injection point must be routed through makeNative
    assert STEALTH_INIT.count("makeNative(") >= 6  # shim + deviceMemory
    # + 2x getParameter + userAgentData getter(s) + henv + toJSON


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_stealth_init_js_syntax():
    """STEALTH_INIT must parse as a valid script (it is an IIFE statement)."""
    from stealth_browser.browser import STEALTH_INIT

    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(STEALTH_INIT + "\n")
        r = subprocess.run(["node", "--check", path],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    finally:
        os.unlink(path)


# --------------------------------------------------------------------------
# open_browser smoke (headless Chromium) — skip if patchright missing
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_browser_smoke():
    patchright = pytest.importorskip("patchright")
    from stealth_browser.browser import open_browser

    p, browser, ctx, profile_dir = await open_browser()
    try:
        page = await ctx.new_page()
        await page.goto("about:blank")
        assert await page.title() == ""
        assert browser is not None
    finally:
        await browser.close()
        await p.stop()


@pytest.mark.asyncio
async def test_apply_stealth_main_world():
    """The spoof must be visible in the page's main world.

    On some patchright builds init scripts run in an isolated world where
    their navigator/WebGL patches never reach page scripts; apply_stealth
    re-applies the same spoof via page.evaluate so the main world sees it.
    """
    patchright = pytest.importorskip("patchright")
    from stealth_browser.browser import apply_stealth, open_browser

    p, browser, ctx, profile_dir = await open_browser()
    try:
        page = await ctx.new_page()
        await page.goto("about:blank")
        await apply_stealth(page)
        r = await page.evaluate(
            """async () => {
                const c = document.createElement('canvas').getContext('webgl');
                const e = c && c.getExtension('WEBGL_debug_renderer_info');
                const uad = navigator.userAgentData;
                const he = uad && uad.getHighEntropyValues
                    ? await uad.getHighEntropyValues(['uaFullVersion'])
                    : null;
                return {
                    deviceMemory: navigator.deviceMemory,
                    renderer: e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'no-gl',
                    uadBrands: uad ? uad.brands.map(b => b.brand) : [],
                    uaFullVersion: he ? he.uaFullVersion : null,
                };
            }"""
        )
        assert r["deviceMemory"] == 8
        assert "AMD" in r["renderer"]
        # UA-CH consistency: flagship brand present and version synced to the UA
        assert "Google Chrome" in r["uadBrands"]
        assert r["uaFullVersion"] == "149.0.7827.55"
    finally:
        await browser.close()
        await p.stop()
