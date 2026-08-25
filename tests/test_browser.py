"""Sanity tests for stealth-browser.

These exercise the human-like interaction helpers and the anti-fingerprint
launch. They need a working patchright install (see pyproject `core`
extra). The `open_browser` smoke test launches a real headless Chromium.

Run:
    pytest -q
"""
import asyncio
import random

import pytest

from stealth_browser.browser import (
    human_delay,
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
    def __init__(self):
        self.typed = []

    async def type(self, ch):
        self.typed.append(ch)


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
    # each character is typed individually, in order
    assert page.keyboard.typed == ["h", "i"]


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
            """() => {
                const c = document.createElement('canvas').getContext('webgl');
                const e = c && c.getExtension('WEBGL_debug_renderer_info');
                return {
                    deviceMemory: navigator.deviceMemory,
                    renderer: e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'no-gl',
                };
            }"""
        )
        assert r["deviceMemory"] == 8
        assert "AMD" in r["renderer"]
    finally:
        await browser.close()
        await p.stop()
