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
        # workers always share the creating document's UA — must match above
        "workerUserAgent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/149.0.7827.55 Safari/537.36"),
        # legacy navigator members must agree with the Chrome UA
        "appVersion": "5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, "
                       "like Gecko) Chrome/149.0.7827.55 Safari/537.36",
        "appCodeName": "Mozilla",
        "product": "Gecko",
        "productSub": "20030107",
        "vendor": "Google Inc.",
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
        "webgl2": "ANGLE (AMD, AMD Radeon Graphics (RADV VEGA10) Direct3D11 "
                  "vs_5_0 ps_5_0, D3D11)",
        "webgl2Vendor": "Google Inc. (AMD)",
        "pluginNames": ["PDF Viewer", "Chrome PDF Viewer",
                        "Chromium PDF Viewer", "Microsoft Edge PDF Viewer",
                        "WebKit built-in PDF"],
        "canvas": "a1b2c3d4",
        # UA-CH (client hints) must match the spoofed Chrome profile
        "uaDataBrands": ('[{"brand": "Google Chrome", "version": "149"}, '
                         '{"brand": "Chromium", "version": "149"}, '
                         '{"brand": "Not)A;Brand", "version": "24"}]'),
        "uaDataMobile": False,
        "uaDataPlatform": "Linux",
        "uaFullVersion": "149.0.7827.55",
        # extended checks (iframe leak, fonts, screen, chrome internals)
        "iframeWebdriver": None,
        "fonts": {"Arial": True, "Times New Roman": True, "Courier New": True,
                  "Verdana": True, "Georgia": True},
        "screenWidth": 1366,
        "screenHeight": 768,
        "screenColorDepth": 24,
        "chromeCsi": True,
        "chromeLoadTimes": True,
        # extended surface probes (audio fingerprint, worker, WebRTC)
        "audioFingerprint": "3a7f9c2b",
        "audioSampleRate": 48000,
        "audioAllZeros": False,
        "workerWebdriver": None,
        "webrtcLeak": {"status": "done", "mdns": 3, "privateIp": 0,
                        "publicIp": 1, "other": 0, "total": 4},
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
# analyze_report — WebGL2 / WebGL1 cross-context consistency
# --------------------------------------------------------------------------
def test_webgl2_swiftshader_leak_is_flagged():
    """A WebGL1-only spoof: WebGL2 still reports the software renderer."""
    r = _clean_results()
    r["webgl2"] = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device ...))"
    r["webgl2Vendor"] = "Google Inc."
    a = analyze_report(r)
    assert a["checks"]["webgl2"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_webgl2_renderer_mismatch_is_flagged():
    """WebGL2 renders with a different (unpatched) GPU than WebGL1 claims."""
    r = _clean_results()
    r["webgl2"] = "ANGLE (Unknown, Mesa llvmpipe (LLVM 15.0.7), OpenGL 4.5)"
    a = analyze_report(r)
    assert a["checks"]["webgl2"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_webgl2_absent_warns():
    """Modern Chrome always ships WebGL2 — its absence is suspicious."""
    r = _clean_results()
    r["webgl2"] = "no-webgl2"
    r["webgl2Vendor"] = "no-webgl2"
    a = analyze_report(r)
    assert a["checks"]["webgl2"]["status"] == "WARN"
    assert a["checks"]["webgl2Vendor"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_webgl2_consistent_passes():
    a = analyze_report(_clean_results())
    assert a["checks"]["webgl2"]["status"] == "PASS"
    assert a["checks"]["webgl2Vendor"]["status"] == "PASS"


# --------------------------------------------------------------------------
# analyze_report — plugin-name realism
# --------------------------------------------------------------------------
def test_plugin_names_with_pdf_viewers_pass():
    a = analyze_report(_clean_results())
    assert a["checks"]["pluginNames"]["status"] == "PASS"


def test_fabricated_plugin_names_warn():
    """Right length, wrong names — a length-only plugin spoof."""
    r = _clean_results()
    r["pluginNames"] = ["Plugin 1", "Plugin 2", "Plugin 3", "Plugin 4",
                        "Plugin 5"]
    a = analyze_report(r)
    assert a["checks"]["pluginNames"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_new_checks_missing_keys_warn_not_crash():
    """Old payloads without the new keys degrade to WARN, never raise."""
    a = analyze_report({})
    assert a["checks"]["webgl2"]["status"] == "WARN"
    assert a["checks"]["webgl2Vendor"]["status"] == "WARN"
    assert a["checks"]["pluginNames"]["status"] == "WARN"
    assert a["checks"]["audioFingerprint"]["status"] == "WARN"
    assert a["checks"]["audioSampleRate"]["status"] == "WARN"
    assert a["checks"]["workerUserAgent"]["status"] == "WARN"
    assert a["checks"]["webrtcLeak"]["status"] == "WARN"
    # webdriver-family checks treat None as clean absence (same as iframe)
    assert a["checks"]["workerWebdriver"]["status"] == "PASS"


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
# analyze_report — UA-CH (client hints) consistency
# --------------------------------------------------------------------------
def test_clean_ua_ch_checks_pass():
    a = analyze_report(_clean_results())
    assert a["checks"]["uaChBrands"]["status"] == "PASS"
    assert a["checks"]["uaChVersion"]["status"] == "PASS"
    assert a["checks"]["uaChPlatform"]["status"] == "PASS"
    assert a["checks"]["uaChMobile"]["status"] == "PASS"


def test_missing_chrome_brand_is_flagged():
    """Headless builds omit the flagship brand — a strong bot signal."""
    r = _clean_results()
    r["uaDataBrands"] = ('[{"brand": "Chromium", "version": "149"}, '
                         '{"brand": "Not)A;Brand", "version": "24"}]')
    a = analyze_report(r)
    assert a["checks"]["uaChBrands"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_ua_full_version_mismatch_is_flagged():
    """Stale build number (e.g. .0 vs the UA's .55) is a headless tell."""
    r = _clean_results()
    r["uaFullVersion"] = "149.0.7827.0"
    a = analyze_report(r)
    assert a["checks"]["uaChVersion"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_ua_platform_mismatch_is_flagged():
    r = _clean_results()
    r["uaDataPlatform"] = "Windows"
    a = analyze_report(r)
    assert a["checks"]["uaChPlatform"]["status"] == "FAIL"


def test_ua_mobile_claim_warns():
    r = _clean_results()
    r["uaDataMobile"] = True
    a = analyze_report(r)
    assert a["checks"]["uaChMobile"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_ua_ch_missing_keys_warn_not_crash():
    """Partial UA-CH data (e.g. old engine without userAgentData) degrades
    to WARN for the version/platform checks, never raises."""
    r = _clean_results()
    del r["uaDataBrands"]
    del r["uaDataMobile"]
    del r["uaDataPlatform"]
    r["uaFullVersion"] = None
    a = analyze_report(r)
    assert a["checks"]["uaChBrands"]["status"] == "FAIL"  # missing = hard signal
    assert a["checks"]["uaChVersion"]["status"] == "WARN"
    assert a["checks"]["uaChPlatform"]["status"] == "WARN"
    assert a["checks"]["uaChMobile"]["status"] == "WARN"


# --------------------------------------------------------------------------
# analyze_report — extended checks (iframe leak, fonts, locale, screen)
# --------------------------------------------------------------------------
def test_iframe_webdriver_leak_is_flagged():
    r = _clean_results()
    r["iframeWebdriver"] = True
    a = analyze_report(r)
    assert a["checks"]["iframeWebdriver"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_iframe_webdriver_string_true_is_flagged():
    r = _clean_results()
    r["iframeWebdriver"] = "true"
    a = analyze_report(r)
    assert a["checks"]["iframeWebdriver"]["status"] == "FAIL"


def test_iframe_webdriver_unverifiable_warns():
    r = _clean_results()
    r["iframeWebdriver"] = "err:SecurityError"
    a = analyze_report(r)
    assert a["checks"]["iframeWebdriver"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_no_standard_fonts_is_flagged():
    r = _clean_results()
    r["fonts"] = {k: False for k in r["fonts"]}
    a = analyze_report(r)
    assert a["checks"]["fonts"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_partially_missing_fonts_warns():
    r = _clean_results()
    fonts = r["fonts"]
    for k in list(fonts)[:2]:
        fonts[k] = False
    a = analyze_report(r)
    assert a["checks"]["fonts"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_fonts_unprobeable_warns():
    r = _clean_results()
    r["fonts"] = "err:no-2d"
    a = analyze_report(r)
    assert a["checks"]["fonts"]["status"] == "WARN"


def test_languages_locale_mismatch_warns():
    r = _clean_results()
    r["languages"] = ["en-US", "en"]
    a = analyze_report(r)
    assert a["checks"]["languages"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_languages_missing_warns():
    r = _clean_results()
    r["languages"] = None
    a = analyze_report(r)
    assert a["checks"]["languages"]["status"] == "WARN"


def test_small_screen_warns():
    r = _clean_results()
    r["screenWidth"], r["screenHeight"] = 800, 600
    a = analyze_report(r)
    assert a["checks"]["screenSize"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_plausible_screen_is_info():
    r = _clean_results()
    r["screenWidth"], r["screenHeight"] = 1920, 1080
    a = analyze_report(r)
    assert a["checks"]["screenSize"]["status"] == "INFO"


def test_chrome_internals_are_info():
    a = analyze_report(_clean_results())
    assert a["checks"]["chromeCsi"]["status"] == "INFO"
    assert a["checks"]["chromeLoadTimes"]["status"] == "INFO"


# --------------------------------------------------------------------------
# analyze_report — extended surface probes (audio fingerprint / worker / WebRTC)
# --------------------------------------------------------------------------
def test_audio_fingerprint_clean_passes():
    a = analyze_report(_clean_results())
    assert a["checks"]["audioFingerprint"]["status"] == "PASS"
    assert a["checks"]["audioSampleRate"]["status"] == "PASS"


def test_audio_all_zeros_is_flagged():
    """All-zero render = degenerate/soft audio stack — a bot signal."""
    r = _clean_results()
    r["audioAllZeros"] = True
    a = analyze_report(r)
    assert a["checks"]["audioFingerprint"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_no_audio_warns():
    r = _clean_results()
    r["audioFingerprint"] = "no-audio"
    a = analyze_report(r)
    assert a["checks"]["audioFingerprint"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_unusual_sample_rate_warns():
    r = _clean_results()
    r["audioSampleRate"] = 8000
    a = analyze_report(r)
    assert a["checks"]["audioSampleRate"]["status"] == "WARN"


def test_worker_webdriver_leak_is_flagged():
    r = _clean_results()
    r["workerWebdriver"] = True
    a = analyze_report(r)
    assert a["checks"]["workerWebdriver"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_worker_webdriver_string_true_is_flagged():
    r = _clean_results()
    r["workerWebdriver"] = "true"
    a = analyze_report(r)
    assert a["checks"]["workerWebdriver"]["status"] == "FAIL"


def test_worker_webdriver_unverifiable_warns():
    r = _clean_results()
    r["workerWebdriver"] = "timeout"
    a = analyze_report(r)
    assert a["checks"]["workerWebdriver"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_worker_ua_mismatch_is_flagged():
    """A UA spoof that misses workers leaks the real UA in worker context."""
    r = _clean_results()
    r["workerUserAgent"] = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) HeadlessChrome/149.0 Safari/537.36")
    a = analyze_report(r)
    assert a["checks"]["workerUserAgent"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_worker_ua_missing_warns():
    r = _clean_results()
    del r["workerUserAgent"]
    a = analyze_report(r)
    assert a["checks"]["workerUserAgent"]["status"] == "WARN"


def test_webrtc_raw_private_ip_is_flagged():
    """Raw RFC1918 IPs in ICE candidates expose the real local IP."""
    r = _clean_results()
    r["webrtcLeak"] = {"status": "done", "mdns": 0, "privateIp": 2,
                       "publicIp": 0, "other": 0, "total": 2}
    a = analyze_report(r)
    assert a["checks"]["webrtcLeak"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_webrtc_mdns_candidates_pass():
    """mDNS-obfuscated host candidates = Chrome's privacy default working."""
    r = _clean_results()
    r["webrtcLeak"] = {"status": "done", "mdns": 2, "privateIp": 0,
                       "publicIp": 0, "other": 0, "total": 2}
    a = analyze_report(r)
    assert a["checks"]["webrtcLeak"]["status"] == "PASS"


def test_webrtc_missing_warns():
    r = _clean_results()
    del r["webrtcLeak"]
    a = analyze_report(r)
    assert a["checks"]["webrtcLeak"]["status"] == "WARN"


def test_webrtc_no_rtcpeerconnection_warns():
    r = _clean_results()
    r["webrtcLeak"] = {"status": "no-webrtc"}
    a = analyze_report(r)
    assert a["checks"]["webrtcLeak"]["status"] == "WARN"


def test_webrtc_error_status_warns():
    r = _clean_results()
    r["webrtcLeak"] = {"status": "err:NotSupportedError"}
    a = analyze_report(r)
    assert a["checks"]["webrtcLeak"]["status"] == "WARN"


# --------------------------------------------------------------------------
# CHECKS — JS payload sanity
# --------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
# --------------------------------------------------------------------------
# legacy navigator members (appVersion/appCodeName/product/productSub/vendor)
# --------------------------------------------------------------------------
def _leak(overrides):
    r = _clean_results()
    r.update(overrides)
    return analyze_report(r)["checks"]


def test_legacy_members_clean_pass():
    checks = _leak({})
    assert checks["appVersion"]["status"] == "PASS"
    assert checks["appCodeName"]["status"] == "PASS"
    assert checks["product"]["status"] == "PASS"
    assert checks["productSub"]["status"] == "PASS"
    assert checks["vendor"]["status"] == "PASS"


def test_headless_leak_in_app_version_is_flagged():
    # headless Chrome leaks HeadlessChrome in appVersion even if the UA is
    # patched — the classic partial-spoof tell
    checks = _leak({"appVersion": "5.0 (X11; Linux) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "HeadlessChrome/149.0.7827.55 Safari/537.36"})
    assert checks["appVersion"]["status"] == "FAIL"


def test_blank_app_version_warns():
    checks = _leak({"appVersion": ""})
    assert checks["appVersion"]["status"] == "WARN"


def test_wrong_app_code_name_warns():
    checks = _leak({"appCodeName": "Netscape"})
    assert checks["appCodeName"]["status"] == "WARN"


def test_wrong_product_warns():
    checks = _leak({"product": ""})
    assert checks["product"]["status"] == "WARN"


def test_missing_product_sub_warns():
    # productSub being null/'' while on Windows/headless is a known tell
    checks = _leak({"productSub": ""})
    assert checks["productSub"]["status"] == "WARN"


def test_empty_vendor_warns():
    checks = _leak({"vendor": ""})
    assert checks["vendor"]["status"] == "WARN"


def test_headless_vendor_leak_fails():
    checks = _leak({"vendor": "HeadlessChrome"})
    assert checks["vendor"]["status"] == "FAIL"


def test_unexpected_vendor_warns():
    checks = _leak({"vendor": "Mozilla Foundation"})
    assert checks["vendor"]["status"] == "WARN"


def test_legacy_members_missing_keys_warn_not_crash():
    r = _clean_results()
    for k in ("appVersion", "appCodeName", "product", "productSub", "vendor"):
        del r[k]
    checks = analyze_report(r)["checks"]
    for name in ("appVersion", "appCodeName", "product", "productSub", "vendor"):
        assert checks[name]["status"] == "WARN"


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
      if (!('webdriver' in r) || !('canvas' in r) || !('permissions' in r)
          || !('iframeWebdriver' in r) || !('fonts' in r)
          || !('webgl2' in r) || !('webgl2Vendor' in r)
          || !('pluginNames' in r)
          || !('audioFingerprint' in r) || !('audioSampleRate' in r)
          || !('audioAllZeros' in r)
          || !('workerWebdriver' in r) || !('workerUserAgent' in r)
          || !('webrtcLeak' in r)) {
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
