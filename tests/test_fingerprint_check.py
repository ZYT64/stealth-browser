"""Unit tests for fingerprint_check: analyze_report classification + JS sanity.

`analyze_report` is pure Python, so these run without a browser. The JS
syntax check shells out to node when available (skipped otherwise).
"""
import shutil
import subprocess
import tempfile
import os

import pytest

from stealth_browser.fingerprint_check import CHECKS, analyze_report


# --------------------------------------------------------------------------
# analyze_report — clean profile
# --------------------------------------------------------------------------
def _clean_results():
    """A profile that matches the expected stealth setup."""
    return {
        "webdriver": None,
        "languages": ["zh-CN", "en"],
        "plugins": 5,
        "chrome": True,
        "chromeRuntime": True,
        "userAgent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/149.0.7827.55 Safari/537.36"),
        "platform": "Linux x86_64",
        "hardwareConcurrency": 8,
        "deviceMemory": 8,
        "maxTouchPoints": 0,
        "devicePixelRatio": 1,
        "viewportDelta": 0,
        "timezoneOffset": -480,
        "timezoneName": "Asia/Shanghai",
        "permissions": "prompt",
        "webglVendor": "Google Inc. (AMD)",
        "webgl": "ANGLE (AMD, AMD Radeon Graphics (RADV VEGA10) Direct3D11 "
                 "vs_5_0 ps_5_0, D3D11)",
        "canvas": "a1b2c3d4",
    }


def test_clean_profile_is_clean():
    a = analyze_report(_clean_results())
    s = a["summary"]
    assert s["failed"] == 0
    assert s["verdict"] == "clean"
    assert a["checks"]["webdriver"]["status"] == "PASS"
    assert a["checks"]["timezone"]["status"] == "PASS"
    assert a["checks"]["permissions"]["status"] == "PASS"


# --------------------------------------------------------------------------
# analyze_report — detection signals
# --------------------------------------------------------------------------
def test_webdriver_true_is_flagged():
    r = _clean_results()
    r["webdriver"] = True
    a = analyze_report(r)
    assert a["checks"]["webdriver"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_headless_ua_is_flagged():
    r = _clean_results()
    r["userAgent"] = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) HeadlessChrome/149.0 Safari/537.36")
    a = analyze_report(r)
    assert a["checks"]["userAgent"]["status"] == "FAIL"


def test_swiftshader_renderer_is_flagged():
    r = _clean_results()
    r["webgl"] = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device ...))"
    r["webglVendor"] = "Google Inc."
    a = analyze_report(r)
    assert a["checks"]["webgl"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_zero_plugins_is_flagged():
    r = _clean_results()
    r["plugins"] = 0
    a = analyze_report(r)
    assert a["checks"]["plugins"]["status"] == "FAIL"


# --------------------------------------------------------------------------
# analyze_report — warnings
# --------------------------------------------------------------------------
def test_device_memory_mismatch_warns():
    r = _clean_results()
    r["deviceMemory"] = 4
    a = analyze_report(r)
    assert a["checks"]["deviceMemory"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_denied_permissions_warns():
    r = _clean_results()
    r["permissions"] = "denied"
    a = analyze_report(r)
    assert a["checks"]["permissions"]["status"] == "WARN"


def test_timezone_mismatch_warns():
    r = _clean_results()
    r["timezoneName"] = "America/New_York"
    r["timezoneOffset"] = 240
    a = analyze_report(r)
    assert a["checks"]["timezone"]["status"] == "WARN"


def test_missing_keys_warn_not_crash():
    a = analyze_report({})  # empty payload must not raise
    s = a["summary"]
    assert s["failed"] > 0  # plugins/webdriver/userAgent all missing -> FAIL
    assert s["warned"] > 0
    assert a["checks"]["deviceMemory"]["status"] == "WARN"


def test_info_checks_are_present():
    a = analyze_report(_clean_results())
    assert a["checks"]["canvas"]["status"] == "INFO"
    assert a["checks"]["platform"]["status"] == "INFO"


# --------------------------------------------------------------------------
# CHECKS — JS payload sanity
# --------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_checks_js_syntax():
    """The injected JS must at least parse as a valid script."""
    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"({CHECKS});\n")  # wrap: async arrow expression statement
        r = subprocess.run(["node", "--check", path],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    finally:
        os.unlink(path)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_checks_js_executes_without_reference_errors():
    """The payload must run inside a minimal DOM stub (no browser needed)."""
    stub = """
    const navigator = {
      webdriver: undefined, languages: ['zh-CN'],
      plugins: {length: 5}, hardwareConcurrency: 8, deviceMemory: 8,
      maxTouchPoints: 0, userAgent: 'Chrome/149', platform: 'Linux x86_64',
      permissions: {query: async () => ({state: 'prompt'})},
    };
    const window = {chrome: {runtime: {id: 'x'}}, innerWidth: 1366,
                    outerWidth: 1366, devicePixelRatio: 1};
    const document = {
      createElement: () => ({
        width: 0, height: 0,
        getContext: () => null,
        toDataURL: () => '',
      }),
    };
    const Intl = {DateTimeFormat: function(){ return {resolvedOptions: () => ({timeZone: 'Asia/Shanghai'})}; }};
    const Date = function(){};
    Date.prototype.getTimezoneOffset = () => -480;
    const result = (""" + CHECKS + """)();
    result.then(r => {
      if (typeof r !== 'object' || r === null) throw new Error('not an object');
      if (!('webdriver' in r) || !('canvas' in r) || !('permissions' in r)) {
        throw new Error('missing keys: ' + Object.keys(r));
      }
      if (r.permissions !== 'prompt') throw new Error('permissions: ' + r.permissions);
      console.log('OK');
    }).catch(e => { console.error(e.message); process.exit(1); });
    """
    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(stub)
        r = subprocess.run(["node", path], capture_output=True, text=True,
                           timeout=30)
        assert r.returncode == 0, r.stderr
    finally:
        os.unlink(path)
