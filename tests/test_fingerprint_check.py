"""Unit tests for fingerprint_check: analyze_report classification + JS sanity.

`analyze_report` is pure Python, so these run without a browser. The JS
syntax check shells out to node when available (skipped otherwise).
"""
import asyncio
import shutil
import subprocess
import tempfile
import os

import pytest

from stealth_browser import fingerprint_check
from stealth_browser.fingerprint_check import CHECKS, analyze_report, header_probe


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
        "viewportDelta": 16,
        # window geometry: real windowed Chrome reserves browser chrome
        # between the viewport and the outer window, and the window
        # (position + outer size) must fit on the screen — open_browser
        # pairs a 1280x600 viewport with a 1366x768 screen and an outer
        # window of 1296x680 at screenX/Y (10,10)
        "innerWidth": 1280,
        "innerHeight": 600,
        "outerWidth": 1296,
        "outerHeight": 680,
        "screenX": 10,
        "screenY": 10,
        "timezoneOffset": -480,
        "timezoneName": "Asia/Shanghai",
        # timezone surface consistency: all three surfaces must agree
        # (getTimezoneOffset convention: UTC+8 -> -480 -> GMT+0800/GMT+8)
        "tzDateOffsetName": "GMT+0800",
        "tzIntlOffsetName": "GMT+8",
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
        # canvas render integrity: valid PNG data URL, non-blank, stable
        "canvasIntegrity": {"status": "ok", "opaque": 312, "dataUrlLen": 2210},
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
        # worker timezone cross-check: workers get fresh Date/Intl from the
        # engine — must agree with the main-frame surfaces above
        "workerTimezoneOffset": -480,
        "workerTimezoneName": "Asia/Shanghai",
        # instance-level webdriver descriptor + host-object identity probes
        "webdriverOwnProp": "none",
        "pluginsConstructor": "[object PluginArray]",
        "mimeTypesConstructor": "[object MimeTypeArray]",
        "webrtcLeak": {"status": "done", "mdns": 3, "privateIp": 0,
                        "publicIp": 1, "other": 0, "total": 4},
        # native toString consistency (spoof-source leak probes): every
        # injected function must stringify to native-looking code
        "fnToStringSelf": "function toString() { [native code] }",
        "webglToString": "function getParameter() { [native code] }",
        "webgl2ToString": "function getParameter() { [native code] }",
        "deviceMemoryGetter": "function get deviceMemory() { [native code] }",
        "uaDataGetter": "function get userAgentData() { [native code] }",
        "uaDataHenv": "function getHighEntropyValues() { [native code] }",
        # permission-surface cross-check + media/mime realism
        "notificationPermission": "default",
        # real desktop Chrome bundles the PDF viewer (Chrome 106+)
        "pdfViewerEnabled": True,
        "mimeTypes": 2,
        "mimeTypeNames": ["application/pdf", "text/pdf"],
        "mediaDevices": {"count": 2, "audioinput": 1, "audiooutput": 1,
                          "videoinput": 0},
        # wire-level HTTP header (CDP probe) must agree with navigator.languages
        "httpAcceptLanguage": "zh-CN,zh;q=0.9",
        # wire-level Sec-CH-UA client hints (CDP probe) must agree with
        # navigator.userAgentData — the spoof above brands Chrome 149 / Linux
        "httpSecChUa": ('"Chromium";v="149", "Google Chrome";v="149", '
                         '"Not;A=Brand";v="99"'),
        "httpSecChUaMobile": "?0",
        "httpSecChUaPlatform": '"Linux"',
    }


def test_clean_profile_is_clean():
    a = analyze_report(_clean_results())
    s = a["summary"]
    assert s["failed"] == 0
    assert s["verdict"] == "clean"
    assert a["checks"]["webdriver"]["status"] == "PASS"
    assert a["checks"]["timezone"]["status"] == "PASS"
    assert a["checks"]["permissions"]["status"] == "PASS"
    assert a["checks"]["windowGeometry"]["status"] == "PASS"


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
    assert a["checks"]["webdriverOwnProp"]["status"] == "PASS"
    # worker timezone cross-check + host-object identity degrades to WARN
    assert a["checks"]["workerTimezoneOffset"]["status"] == "WARN"
    assert a["checks"]["workerTimezoneName"]["status"] == "WARN"
    assert a["checks"]["pluginsConstructor"]["status"] == "WARN"
    assert a["checks"]["mimeTypesConstructor"]["status"] == "WARN"
    # permission-surface cross-check + media/mime realism
    assert a["checks"]["notificationPermission"]["status"] == "WARN"
    assert a["checks"]["mimeTypes"]["status"] == "WARN"
    assert a["checks"]["mediaDevices"]["status"] == "WARN"
    # wire header probe missing -> cannot verify, not a leak
    assert a["checks"]["httpAcceptLanguage"]["status"] == "WARN"


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


# --------------------------------------------------------------------------
# analyze_report — timezone surface consistency + pdfViewerEnabled
# --------------------------------------------------------------------------
def test_timezone_consistency_agreement_passes():
    a = analyze_report(_clean_results())
    c = a["checks"]["timezoneConsistency"]
    assert c["status"] == "PASS"
    assert "all readable timezone surfaces agree" in c["note"]


def test_timezone_date_tostring_mismatch_is_flagged():
    """A spoof that rewrites Intl but not Date leaves the abbreviations
    disagreeing — the same class of partial-spoof leak as the WebGL1/2
    cross-check."""
    r = _clean_results()
    r["tzDateOffsetName"] = "GMT+0000"
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_timezone_intl_mismatch_is_flagged():
    r = _clean_results()
    r["tzIntlOffsetName"] = "GMT+9"
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "FAIL"


def test_timezone_consistency_offset_vs_date_only_can_flag():
    """Even without the Intl surface, a bad Date.toString abbreviation must
    disagree with getTimezoneOffset — two readable surfaces suffice."""
    r = _clean_results()
    del r["tzIntlOffsetName"]
    r["tzDateOffsetName"] = "GMT-0800"
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "FAIL"


def test_timezone_consistency_half_hour_offsets_parse():
    """Half-hour zones: +05:30 must round-trip from both abbrev shapes."""
    r = _clean_results()
    r["timezoneName"] = "Asia/Kolkata"  # the profile check warns; fine here
    r["timezoneOffset"] = -330
    r["tzDateOffsetName"] = "GMT+0530"
    r["tzIntlOffsetName"] = "GMT+5:30"
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "PASS"


def test_timezone_consistency_west_of_utc_sign_convention():
    """UTC-6: getTimezoneOffset=+360 (minutes west) vs GMT-0600 — the
    convention flip is the bug this test pins down."""
    r = _clean_results()
    r["timezoneName"] = "America/Chicago"
    r["timezoneOffset"] = 360
    r["tzDateOffsetName"] = "GMT-0600"
    r["tzIntlOffsetName"] = "GMT-6"
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "PASS"


def test_timezone_consistency_unparseable_surface_warns():
    """Error strings are 'cannot verify', never a leak: one broken surface
    leaves two healthy surfaces to cross-check (PASS, not FAIL); down to a
    single surviving surface the verdict degrades to WARN."""
    r = _clean_results()
    r["tzDateOffsetName"] = "err:RangeError"
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "PASS"
    assert a["summary"]["verdict"] != "flagged"

    r["tzIntlOffsetName"] = None
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "WARN"
    assert a["summary"]["verdict"] != "flagged"


def test_timezone_consistency_single_surface_warns():
    r = _clean_results()
    del r["tzDateOffsetName"]
    del r["tzIntlOffsetName"]
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "WARN"


def test_timezone_consistency_all_missing_warns_not_crashes():
    r = _clean_results()
    del r["tzDateOffsetName"]
    del r["tzIntlOffsetName"]
    r["timezoneOffset"] = None
    a = analyze_report(r)
    assert a["checks"]["timezoneConsistency"]["status"] == "WARN"


def test_pdf_viewer_enabled_passes():
    a = analyze_report(_clean_results())
    assert a["checks"]["pdfViewerEnabled"]["status"] == "PASS"


def test_pdf_viewer_disabled_warns():
    """Headless shells report false — a warning, not a hard leak."""
    r = _clean_results()
    r["pdfViewerEnabled"] = False
    a = analyze_report(r)
    assert a["checks"]["pdfViewerEnabled"]["status"] == "WARN"
    assert a["summary"]["verdict"] != "flagged"


def test_pdf_viewer_missing_warns():
    r = _clean_results()
    del r["pdfViewerEnabled"]
    a = analyze_report(r)
    assert a["checks"]["pdfViewerEnabled"]["status"] == "WARN"


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
    # Drop the wire hint so the httpSecChUaMobile cross-check cannot run:
    # a mobile claim WITH a wire 'not mobile' hint is a hard FAIL there
    # (see test_sec_ch_ua_mobile_cross_check) — this test targets uaChMobile.
    del r["httpSecChUaMobile"]
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
    # Keep the wire header consistent with the (mis-set) JS locale: this
    # test isolates the languages-vs-EXPECTED check. A zh-CN header next to
    # en-US languages would be a header/JS mismatch — its own FAIL (see the
    # wire Accept-Language tests below).
    r["httpAcceptLanguage"] = "en-US,en;q=0.9"
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
    # keep the window geometry coherent with the smaller screen (the outer
    # window must still fit) so this test isolates the screenSize WARN
    # instead of tripping the windowGeometry cross-check
    r["screenX"], r["screenY"] = 0, 0
    r["innerWidth"], r["innerHeight"] = 768, 470
    r["outerWidth"], r["outerHeight"] = 784, 550
    r["viewportDelta"] = 16
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
# analyze_report — window geometry (windowed vs headless window surface)
# --------------------------------------------------------------------------
def test_window_geometry_windowed_profile_passes():
    a = analyze_report(_clean_results())
    c = a["checks"]["windowGeometry"]
    assert c["status"] == "PASS"
    assert "1296x680" in c["note"]


def test_window_geometry_equal_inner_outer_fails():
    """Headless profile: no real OS window, outer == inner on both axes."""
    r = _clean_results()
    r["viewportDelta"] = 0
    r["outerWidth"], r["outerHeight"] = r["innerWidth"], r["innerHeight"]
    a = analyze_report(r)
    c = a["checks"]["windowGeometry"]
    assert c["status"] == "FAIL"
    assert "headless geometry" in c["note"]
    assert a["summary"]["verdict"] == "flagged"


def test_window_geometry_outer_smaller_than_inner_fails():
    """Impossible geometry: the viewport can never exceed the outer window."""
    r = _clean_results()
    r["outerWidth"], r["outerHeight"] = 1200, 580
    a = analyze_report(r)
    c = a["checks"]["windowGeometry"]
    assert c["status"] == "FAIL"
    assert "smaller than inner" in c["note"]


def test_window_geometry_width_delta_only_is_consistent():
    """Linux maximized windows report outerWidth == innerWidth but real
    chrome height — a partial equality is coherent, never a FAIL."""
    r = _clean_results()
    r["outerWidth"] = r["innerWidth"]
    r["viewportDelta"] = 0
    a = analyze_report(r)
    assert a["checks"]["windowGeometry"]["status"] == "PASS"


def test_window_geometry_outer_exceeds_screen_fails():
    """The outer window can never be larger than the screen it renders on."""
    r = _clean_results()
    r["outerWidth"], r["outerHeight"] = 1920, 680
    a = analyze_report(r)
    c = a["checks"]["windowGeometry"]
    assert c["status"] == "FAIL"
    assert "exceeds screen" in c["note"]


def test_window_geometry_position_overflow_fails():
    """Position + outer size must stay inside the screen (window at 10,10
    with outer 1296x680 fits a 1366x768 screen; nudging it right overflows)."""
    r = _clean_results()
    r["screenX"], r["screenY"] = 80, 120
    a = analyze_report(r)
    c = a["checks"]["windowGeometry"]
    assert c["status"] == "FAIL"
    assert "overflows screen" in c["note"]


def test_window_geometry_position_at_origin_fits():
    r = _clean_results()
    r["screenX"], r["screenY"] = 0, 0
    a = analyze_report(r)
    assert a["checks"]["windowGeometry"]["status"] == "PASS"


def test_window_geometry_missing_keys_warn_not_crash():
    r = _clean_results()
    for k in ("innerWidth", "innerHeight", "outerWidth", "outerHeight"):
        del r[k]
    a = analyze_report(r)
    c = a["checks"]["windowGeometry"]
    assert c["status"] == "WARN"
    assert a["summary"]["failed"] == 0


def test_window_geometry_position_missing_still_checks_invariants():
    """screenX/Y unreadable: inner/outer invariants are still enforced (the
    fit-on-screen cross-check is simply skipped)."""
    r = _clean_results()
    del r["screenX"], r["screenY"]
    a = analyze_report(r)
    assert a["checks"]["windowGeometry"]["status"] == "PASS"
    r2 = _clean_results()
    r2["outerHeight"] = 800  # exceeds the 768 screen with no position needed
    del r2["screenX"], r2["screenY"]
    a2 = analyze_report(r2)
    assert a2["checks"]["windowGeometry"]["status"] == "FAIL"


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


# --------------------------------------------------------------------------
# analyze_report — canvas render integrity
# --------------------------------------------------------------------------
def test_canvas_integrity_clean_passes():
    a = analyze_report(_clean_results())
    assert a["checks"]["canvasIntegrity"]["status"] == "PASS"


def test_canvas_blank_is_flagged():
    """All-transparent readback = blanking spoof / broken rasterizer."""
    r = _clean_results()
    r["canvasIntegrity"] = {"status": "blank", "opaque": 0, "dataUrlLen": 142}
    a = analyze_report(r)
    assert a["checks"]["canvasIntegrity"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_canvas_unstable_render_is_flagged():
    """Two identical draws producing different data URLs = noise-injection spoof."""
    r = _clean_results()
    r["canvasIntegrity"] = {"status": "unstable-render", "opaque": 312,
                             "dataUrlLen": 2210}
    a = analyze_report(r)
    assert a["checks"]["canvasIntegrity"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_canvas_unstable_readback_is_flagged():
    """getImageData returning different bytes per call = readback noise spoof."""
    r = _clean_results()
    r["canvasIntegrity"] = {"status": "unstable-readback", "opaque": 312,
                             "dataUrlLen": 2210}
    a = analyze_report(r)
    assert a["checks"]["canvasIntegrity"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_canvas_bad_data_url_is_flagged():
    """toDataURL not returning a PNG data URL = patched canvas API."""
    r = _clean_results()
    r["canvasIntegrity"] = {"status": "bad-data-url"}
    a = analyze_report(r)
    assert a["checks"]["canvasIntegrity"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_canvas_probe_error_warns():
    """A thrown probe error is 'cannot verify', never a leak."""
    r = _clean_results()
    r["canvasIntegrity"] = {"status": "err:TypeError"}
    a = analyze_report(r)
    assert a["checks"]["canvasIntegrity"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_canvas_integrity_missing_warns():
    r = _clean_results()
    del r["canvasIntegrity"]
    a = analyze_report(r)
    assert a["checks"]["canvasIntegrity"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_canvas_integrity_unreadable_warns():
    r = _clean_results()
    r["canvasIntegrity"] = "no-canvas"
    a = analyze_report(r)
    assert a["checks"]["canvasIntegrity"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_canvas_integrity_unknown_status_warns():
    r = _clean_results()
    r["canvasIntegrity"] = {"status": "something-new"}
    a = analyze_report(r)
    assert a["checks"]["canvasIntegrity"]["status"] == "WARN"


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


# --------------------------------------------------------------------------
# analyze_report — worker timezone cross-check (cross-realm spoof leaks)
# --------------------------------------------------------------------------
def test_worker_timezone_match_passes():
    a = analyze_report(_clean_results())
    assert a["checks"]["workerTimezoneOffset"]["status"] == "PASS"
    assert a["checks"]["workerTimezoneName"]["status"] == "PASS"


def test_worker_timezone_offset_mismatch_is_flagged():
    """A timezone patch layered in the main world (init script/extension)
    never reaches workers' fresh Date objects — the offsets disagree."""
    r = _clean_results()
    r["workerTimezoneOffset"] = 300
    a = analyze_report(r)
    assert a["checks"]["workerTimezoneOffset"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_worker_timezone_name_mismatch_is_flagged():
    r = _clean_results()
    r["workerTimezoneName"] = "America/New_York"
    a = analyze_report(r)
    assert a["checks"]["workerTimezoneName"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_worker_timezone_float_offset_normalizes():
    """Engines may hand back 480.0 — the comparison must still match."""
    r = _clean_results()
    r["workerTimezoneOffset"] = -480.0
    r["timezoneOffset"] = -480.0
    a = analyze_report(r)
    assert a["checks"]["workerTimezoneOffset"]["status"] == "PASS"


def test_worker_timezone_unreadable_warns():
    """Error/timeout strings are 'cannot verify', never a leak."""
    r = _clean_results()
    r["workerTimezoneOffset"] = "timeout"
    r["workerTimezoneName"] = "err:RangeError"
    a = analyze_report(r)
    assert a["checks"]["workerTimezoneOffset"]["status"] == "WARN"
    assert a["checks"]["workerTimezoneName"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_worker_timezone_missing_warns():
    r = _clean_results()
    del r["workerTimezoneOffset"]
    del r["workerTimezoneName"]
    a = analyze_report(r)
    assert a["checks"]["workerTimezoneOffset"]["status"] == "WARN"
    assert a["checks"]["workerTimezoneName"]["status"] == "WARN"


# --------------------------------------------------------------------------
# analyze_report — instance-level webdriver descriptor + host-object identity
# --------------------------------------------------------------------------
def test_webdriver_own_prop_clean_passes():
    """Real Chrome keeps webdriver on the prototype (patchright removes it
    there) — the instance carries no own property."""
    a = analyze_report(_clean_results())
    assert a["checks"]["webdriverOwnProp"]["status"] == "PASS"


def test_webdriver_own_prop_getter_is_flagged():
    """Layered spoof: defineProperty(navigator, 'webdriver', {get: ...})."""
    r = _clean_results()
    r["webdriverOwnProp"] = "own-getter"
    a = analyze_report(r)
    assert a["checks"]["webdriverOwnProp"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_webdriver_own_prop_value_is_flagged():
    r = _clean_results()
    r["webdriverOwnProp"] = "own-value"
    a = analyze_report(r)
    assert a["checks"]["webdriverOwnProp"]["status"] == "FAIL"


def test_webdriver_own_prop_error_warns():
    r = _clean_results()
    r["webdriverOwnProp"] = "err:TypeError"
    a = analyze_report(r)
    assert a["checks"]["webdriverOwnProp"]["status"] == "WARN"


def test_host_object_identity_clean_passes():
    a = analyze_report(_clean_results())
    assert a["checks"]["pluginsConstructor"]["status"] == "PASS"
    assert a["checks"]["mimeTypesConstructor"]["status"] == "PASS"


def test_js_array_plugin_spoof_is_flagged():
    """A plain JS array of the right length fails the PluginArray identity
    probe even when the fabricated names look right."""
    r = _clean_results()
    r["pluginsConstructor"] = "[object Array]"
    a = analyze_report(r)
    assert a["checks"]["pluginsConstructor"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_js_array_mimetypes_spoof_is_flagged():
    r = _clean_results()
    r["mimeTypesConstructor"] = "[object Array]"
    a = analyze_report(r)
    assert a["checks"]["mimeTypesConstructor"]["status"] == "FAIL"


def test_host_object_identity_missing_warn_not_crash():
    r = _clean_results()
    del r["pluginsConstructor"]
    del r["mimeTypesConstructor"]
    a = analyze_report(r)
    assert a["checks"]["pluginsConstructor"]["status"] == "WARN"
    assert a["checks"]["mimeTypesConstructor"]["status"] == "WARN"
    assert a["summary"]["verdict"] != "flagged"


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
# analyze_report — permission-surface cross-check (Notification vs query)
# --------------------------------------------------------------------------
def test_notification_permission_consistent_passes():
    r = _clean_results()
    r["permissions"] = "prompt"
    r["notificationPermission"] = "default"
    a = analyze_report(r)
    assert a["checks"]["notificationPermission"]["status"] == "PASS"
    assert a["summary"]["verdict"] == "clean"


def test_notification_permission_both_granted_passes():
    r = _clean_results()
    r["permissions"] = "granted"
    r["notificationPermission"] = "granted"
    a = analyze_report(r)
    assert a["checks"]["notificationPermission"]["status"] == "PASS"


def test_notification_permission_both_denied_passes():
    r = _clean_results()
    r["permissions"] = "denied"
    r["notificationPermission"] = "denied"
    a = analyze_report(r)
    assert a["checks"]["notificationPermission"]["status"] == "PASS"


def test_notification_permission_denied_mismatch_is_flagged():
    # The sannysoft "Permissions" tell: one surface patched, the other not.
    r = _clean_results()
    r["permissions"] = "prompt"
    r["notificationPermission"] = "denied"
    a = analyze_report(r)
    assert a["checks"]["notificationPermission"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_notification_permission_granted_mismatch_is_flagged():
    r = _clean_results()
    r["permissions"] = "prompt"
    r["notificationPermission"] = "granted"
    a = analyze_report(r)
    assert a["checks"]["notificationPermission"]["status"] == "FAIL"


def test_notification_permission_missing_warns():
    r = _clean_results()
    del r["notificationPermission"]
    a = analyze_report(r)
    assert a["checks"]["notificationPermission"]["status"] == "WARN"


def test_notification_permission_without_query_warns():
    r = _clean_results()
    r["permissions"] = "err:TypeError"
    a = analyze_report(r)
    assert a["checks"]["notificationPermission"]["status"] == "WARN"


def test_notification_permission_no_api_warns():
    r = _clean_results()
    r["notificationPermission"] = "no-notification-api"
    a = analyze_report(r)
    assert a["checks"]["notificationPermission"]["status"] == "WARN"


# --------------------------------------------------------------------------
# analyze_report — MIME-type realism (length-only plugin spoofs)
# --------------------------------------------------------------------------
def test_mime_types_with_pdf_pass():
    r = _clean_results()
    a = analyze_report(r)
    assert a["checks"]["mimeTypes"]["status"] == "PASS"


def test_length_only_plugin_spoof_warns():
    # Fabricated plugin array of the right length but no matching MIME types.
    r = _clean_results()
    r["mimeTypes"] = 0
    r["mimeTypeNames"] = []
    a = analyze_report(r)
    assert a["checks"]["mimeTypes"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_mime_types_without_pdf_warn():
    r = _clean_results()
    r["mimeTypeNames"] = ["application/x-fake"]
    a = analyze_report(r)
    assert a["checks"]["mimeTypes"]["status"] == "WARN"


def test_mime_types_missing_warns():
    r = _clean_results()
    del r["mimeTypes"]
    del r["mimeTypeNames"]
    a = analyze_report(r)
    assert a["checks"]["mimeTypes"]["status"] == "WARN"


def test_mime_types_probe_error_warns():
    r = _clean_results()
    r["mimeTypes"] = "err:TypeError"
    r["mimeTypeNames"] = "err:TypeError"
    a = analyze_report(r)
    assert a["checks"]["mimeTypes"]["status"] == "WARN"


# --------------------------------------------------------------------------
# analyze_report — media device enumeration
# --------------------------------------------------------------------------
def test_media_devices_present_passes():
    r = _clean_results()
    a = analyze_report(r)
    assert a["checks"]["mediaDevices"]["status"] == "PASS"


def test_media_devices_empty_warns():
    # Headless shells report an empty enumerateDevices list.
    r = _clean_results()
    r["mediaDevices"] = {"count": 0, "audioinput": 0, "audiooutput": 0,
                          "videoinput": 0}
    a = analyze_report(r)
    assert a["checks"]["mediaDevices"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_media_devices_missing_warns():
    r = _clean_results()
    del r["mediaDevices"]
    a = analyze_report(r)
    assert a["checks"]["mediaDevices"]["status"] == "WARN"


def test_media_devices_probe_error_warns():
    r = _clean_results()
    r["mediaDevices"] = "err:NotAllowedError"
    a = analyze_report(r)
    assert a["checks"]["mediaDevices"]["status"] == "WARN"


def test_media_devices_no_api_warns():
    r = _clean_results()
    r["mediaDevices"] = "no-media-devices"
    a = analyze_report(r)
    assert a["checks"]["mediaDevices"]["status"] == "WARN"


# --------------------------------------------------------------------------
# analyze_report — wire Accept-Language vs navigator.languages (header/JS)
# --------------------------------------------------------------------------
def test_wire_accept_language_match_passes():
    a = analyze_report(_clean_results())
    assert a["checks"]["httpAcceptLanguage"]["status"] == "PASS"
    assert a["summary"]["verdict"] == "clean"


def test_wire_accept_language_case_insensitive_match():
    """Language tags are case-insensitive (BCP47) — 'zh-cn' == 'zh-CN'."""
    r = _clean_results()
    r["httpAcceptLanguage"] = "zh-cn,zh;q=0.9"
    a = analyze_report(r)
    assert a["checks"]["httpAcceptLanguage"]["status"] == "PASS"


def test_wire_accept_language_mismatch_is_flagged():
    """JS-only locale spoof: navigator.languages patched, wire header left
    at the context's real locale — the classic header/JS mismatch."""
    r = _clean_results()
    r["httpAcceptLanguage"] = "en-US,en;q=0.9"
    a = analyze_report(r)
    assert a["checks"]["httpAcceptLanguage"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_wire_accept_language_wildcard_is_flagged():
    """Real Chrome never sends '*' — a rewritten/anonymous header disagrees
    with navigator.languages just like a spoof would."""
    r = _clean_results()
    r["httpAcceptLanguage"] = "*"
    a = analyze_report(r)
    assert a["checks"]["httpAcceptLanguage"]["status"] == "FAIL"


def test_wire_accept_language_missing_warns():
    r = _clean_results()
    del r["httpAcceptLanguage"]
    a = analyze_report(r)
    assert a["checks"]["httpAcceptLanguage"]["status"] == "WARN"


def test_wire_accept_language_capture_error_warns():
    r = _clean_results()
    r["httpAcceptLanguage"] = "err:TargetClosedError"
    a = analyze_report(r)
    assert a["checks"]["httpAcceptLanguage"]["status"] == "WARN"


def test_wire_accept_language_without_languages_warns():
    """Header captured but navigator.languages missing — no cross-check."""
    r = _clean_results()
    r["languages"] = None
    a = analyze_report(r)
    assert a["checks"]["httpAcceptLanguage"]["status"] == "WARN"


# --------------------------------------------------------------------------
# header_probe — CDP wire capture (fake CDP session, no browser needed)
# --------------------------------------------------------------------------
class _FakeCDP:
    """Minimal CDP session: records handlers, replays canned request events
    once Network.enable is called — mirrors the real event flow closely
    enough to test the capture logic without a browser."""

    def __init__(self, events):
        self._events = events
        self.handlers = {}
        self.detached = False

    def on(self, event, fn):
        self.handlers.setdefault(event, []).append(fn)

    async def send(self, method, params=None):
        if method == "Network.enable":
            for evt in self._events:
                for fn in self.handlers.get("Network.requestWillBeSent", []):
                    fn(evt)

    async def detach(self):
        self.detached = True


class _FakeContext:
    def __init__(self, cdp):
        self._cdp = cdp

    async def new_cdp_session(self, page):
        return self._cdp


class _FakePage:
    """Duck-typed stand-in: evaluate is fire-and-forget (the fake CDP already
    delivered its events during Network.enable)."""

    def __init__(self, cdp):
        self.context = _FakeContext(cdp)

    async def evaluate(self, script):
        return None


def _req_event(headers):
    return {"request": {"url": "https://example.com/favicon.ico",
                        "method": "GET", "headers": headers}}


def _probe_out(**overrides):
    """Expected header_probe result shape: all four captured keys, defaulting
    to None (no capture) with the given overrides filled in."""
    out = {key: None for key in fingerprint_check._PROBE_HEADER_KEYS}
    out.update(overrides)
    return out


async def test_header_probe_captures_accept_language():
    cdp = _FakeCDP([_req_event({"Accept-Language": "zh-CN,zh;q=0.9",
                                 "User-Agent": "Chrome/149"})])
    out = await header_probe(_FakePage(cdp))
    assert out == _probe_out(httpAcceptLanguage="zh-CN,zh;q=0.9")
    assert cdp.detached  # session always cleaned up


async def test_header_probe_header_casing_insensitive():
    """CDP header casing varies across versions — lowercase must match too."""
    cdp = _FakeCDP([_req_event({"accept-language": "zh-CN,zh;q=0.9"})])
    out = await header_probe(_FakePage(cdp))
    assert out == _probe_out(httpAcceptLanguage="zh-CN,zh;q=0.9")


async def test_header_probe_uses_first_matching_request():
    """Later requests must not overwrite the first captured header."""
    cdp = _FakeCDP([
        _req_event({"accept-language": "zh-CN,zh;q=0.9"}),
        _req_event({"accept-language": "en-US,en;q=0.9"}),
    ])
    out = await header_probe(_FakePage(cdp))
    assert out == _probe_out(httpAcceptLanguage="zh-CN,zh;q=0.9")


async def test_header_probe_captures_sec_ch_ua_family():
    """The default UA client hints ride the same request as Accept-Language
    and must be snapshotted together so the wire/JS cross-checks compare
    one coherent request (casing-insensitive, like the other headers)."""
    cdp = _FakeCDP([_req_event({
        "Accept-Language": "zh-CN,zh;q=0.9",
        "sec-ch-ua": ('"Chromium";v="149", "Google Chrome";v="149", '
                       '"Not;A=Brand";v="99"'),
        "SEC-CH-UA-MOBILE": "?0",
        "Sec-CH-UA-Platform": '"Linux"',
    })])
    out = await header_probe(_FakePage(cdp))
    assert out == _probe_out(
        httpAcceptLanguage="zh-CN,zh;q=0.9",
        httpSecChUa=('"Chromium";v="149", "Google Chrome";v="149", '
                      '"Not;A=Brand";v="99"'),
        httpSecChUaMobile="?0",
        httpSecChUaPlatform='"Linux"',
    )


async def test_header_probe_sec_ch_ua_absent_means_none():
    """A request without the client hints (e.g. a non-secure destination)
    records None for them — 'not sent', never a fabricated value."""
    cdp = _FakeCDP([_req_event({"Accept-Language": "zh-CN,zh;q=0.9"})])
    out = await header_probe(_FakePage(cdp))
    assert out == _probe_out(httpAcceptLanguage="zh-CN,zh;q=0.9")


async def test_header_probe_no_matching_request_returns_none(monkeypatch):
    """No request carrying Accept-Language (about:blank fallback, blocked
    fetch, headerless engine) -> None, i.e. 'cannot verify' — not a leak."""
    monkeypatch.setattr(fingerprint_check, "_HEADER_PROBE_TIMEOUT", 0.05)
    cdp = _FakeCDP([_req_event({"User-Agent": "Chrome/149"})])
    out = await header_probe(_FakePage(cdp))
    assert out == _probe_out()


async def test_header_probe_no_events_at_all_returns_none(monkeypatch):
    monkeypatch.setattr(fingerprint_check, "_HEADER_PROBE_TIMEOUT", 0.05)
    out = await header_probe(_FakePage(_FakeCDP([])))
    assert out == _probe_out()


async def test_header_probe_session_error_reports_err():
    """A page/context without CDP support degrades to err:<name>, never
    raises — cmd_check must keep working for the remaining checks."""

    class _NoCDPPage:
        pass  # no .context — new_cdp_session unavailable

    out = await header_probe(_NoCDPPage())
    assert out["httpAcceptLanguage"].startswith("err:")
    assert out["httpSecChUa"].startswith("err:")
    assert out["httpSecChUaMobile"].startswith("err:")
    assert out["httpSecChUaPlatform"].startswith("err:")


# --------------------------------------------------------------------------
# analyze_report — wire-vs-JS Sec-CH-UA client-hints cross-check
# --------------------------------------------------------------------------
def test_sec_ch_ua_wire_matches_js_is_pass():
    r = _clean_results()
    a = analyze_report(r)
    c = a["checks"]["httpSecChUa"]
    assert c["status"] == "PASS"
    assert "Google Chrome 149" in c["note"]


def test_sec_ch_ua_version_mismatch_is_flagged():
    """A UA override that leaves the engine's client hints behind (wire says
    148, JS spoof says 149) is exactly the mismatch server-side detectors
    probe for — and one no in-page JS check can ever see."""
    r = _clean_results()
    r["httpSecChUa"] = ('"Chromium";v="148", "Google Chrome";v="148", '
                          '"Not;A=Brand";v="99"')
    a = analyze_report(r)
    c = a["checks"]["httpSecChUa"]
    assert c["status"] == "FAIL"
    assert "148 on the wire vs 149 in JS" in c["note"]


def test_sec_ch_ua_wire_missing_chrome_brand_is_flagged():
    """A headless-style wire hint (Chromium only, no Google Chrome) against
    a JS spoof advertising the flagship brand — JS-only UA-CH spoof tell."""
    r = _clean_results()
    r["httpSecChUa"] = '"Chromium";v="149", "Not;A=Brand";v="99"'
    a = analyze_report(r)
    assert a["checks"]["httpSecChUa"]["status"] == "FAIL"


def test_sec_ch_ua_grease_difference_is_not_flagged():
    """The grease brand rotates per session ('Not;A=Brand' vs 'Not:A-Brand'
    vs the spoof's 'Not)A;Brand') — a differing grease must stay PASS."""
    r = _clean_results()
    r["httpSecChUa"] = ('"Google Chrome";v="149", "Not:A-Brand";v="8", '
                          '"Chromium";v="149"')
    a = analyze_report(r)
    assert a["checks"]["httpSecChUa"]["status"] == "PASS"


def test_sec_ch_ua_missing_wire_is_warn():
    r = _clean_results()
    del r["httpSecChUa"]
    a = analyze_report(r)
    assert a["checks"]["httpSecChUa"]["status"] == "WARN"


def test_sec_ch_ua_err_is_warn():
    r = _clean_results()
    r["httpSecChUa"] = "err:TargetClosedError"
    a = analyze_report(r)
    assert a["checks"]["httpSecChUa"]["status"] == "WARN"


def test_sec_ch_ua_malformed_wire_is_warn():
    r = _clean_results()
    r["httpSecChUa"] = "garbage"
    a = analyze_report(r)
    assert a["checks"]["httpSecChUa"]["status"] == "WARN"


def test_sec_ch_ua_js_brands_missing_is_warn():
    """Without a JS-side brands snapshot the cross-check cannot run —
    'cannot verify' (the missing userAgentData itself is flagged by
    uaChBrands, not here)."""
    r = _clean_results()
    del r["uaDataBrands"]
    a = analyze_report(r)
    assert a["checks"]["httpSecChUa"]["status"] == "WARN"


def test_sec_ch_ua_mobile_cross_check():
    r = _clean_results()
    a = analyze_report(r)
    assert a["checks"]["httpSecChUaMobile"]["status"] == "PASS"
    r["httpSecChUaMobile"] = "?1"  # desktop profile claiming mobile on the wire
    a = analyze_report(r)
    assert a["checks"]["httpSecChUaMobile"]["status"] == "FAIL"
    r["httpSecChUaMobile"] = "bogus"
    a = analyze_report(r)
    assert a["checks"]["httpSecChUaMobile"]["status"] == "WARN"
    del r["httpSecChUaMobile"]
    a = analyze_report(r)
    assert a["checks"]["httpSecChUaMobile"]["status"] == "WARN"


def test_sec_ch_ua_platform_cross_check():
    r = _clean_results()
    a = analyze_report(r)
    assert a["checks"]["httpSecChUaPlatform"]["status"] == "PASS"
    r["httpSecChUaPlatform"] = '"Windows"'
    a = analyze_report(r)
    assert a["checks"]["httpSecChUaPlatform"]["status"] == "FAIL"
    del r["httpSecChUaPlatform"]
    a = analyze_report(r)
    assert a["checks"]["httpSecChUaPlatform"]["status"] == "WARN"


def test_sec_ch_ua_parsers():
    parse = fingerprint_check._parse_sec_ch_ua
    assert parse('"Chromium";v="149", "Not;A=Brand";v="99"') == [
        ("Chromium", "149"), ("Not;A=Brand", "99")]
    assert parse("garbage") is None
    assert parse("") is None
    assert parse(None) is None
    plat = fingerprint_check._parse_sec_ch_ua_platform
    assert plat('"Linux"') == "Linux"
    assert plat('"Chrome OS"') == "Chrome OS"
    assert plat("Linux") == "Linux"  # tolerate unquoted values
    assert plat("") is None
    brands = fingerprint_check._parse_ua_data_brands
    assert brands('[{"brand": "Google Chrome", "version": "149"}]') == [
        ("Google Chrome", "149")]
    assert brands(None) is None
    assert brands("not json") is None
    assert brands("{}") is None
    assert fingerprint_check._brand_mismatches(
        [("Google Chrome", "149"), ("Chromium", "149")],
        [("Google Chrome", "149"), ("Chromium", "149")]) == []


# --------------------------------------------------------------------------
# analyze_report — native toString consistency (spoof-source leaks)
# --------------------------------------------------------------------------
def test_webgl_tostring_leak_is_flagged():
    """A patched getParameter still showing its JS source is an instant tell:
    the source contains the hardcoded vendor id and renderer constants."""
    r = _clean_results()
    r["webglToString"] = ("function(p) { if (p === 37445) return 'Google Inc. (AMD)'; "
                          "if (p === 37446) return 'ANGLE (AMD, AMD Radeon ...'; "
                          "return orig.call(this, p); }")
    a = analyze_report(r)
    assert a["checks"]["webglToString"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_webgl2_tostring_leak_is_flagged():
    r = _clean_results()
    r["webgl2ToString"] = ("p => p === 37446 ? 'ANGLE (AMD, AMD Radeon Graphics)' "
                           ": orig(p)")
    a = analyze_report(r)
    assert a["checks"]["webgl2ToString"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_fn_tostring_shim_leak_is_flagged():
    """A toString shim whose own source leaks is worse than no shim: it
    proves Function.prototype was tampered with."""
    r = _clean_results()
    r["fnToStringSelf"] = ("function toString() { if (spoofedFns.has(this)) "
                           "return 'function ' + name + '() { [native code] }'; }")
    a = analyze_report(r)
    assert a["checks"]["fnToStringSelf"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_device_memory_getter_arrow_leak_is_flagged():
    r = _clean_results()
    r["deviceMemoryGetter"] = "() => 8"
    a = analyze_report(r)
    assert a["checks"]["deviceMemoryGetter"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_uad_henv_leak_is_flagged():
    r = _clean_results()
    r["uaDataHenv"] = "() => Promise.resolve({uaFullVersion: '149.0.7827.55'})"
    a = analyze_report(r)
    assert a["checks"]["uaDataHenv"]["status"] == "FAIL"
    assert a["summary"]["verdict"] == "flagged"


def test_tostring_probes_missing_warn_not_crash():
    """Old payloads without the toString keys degrade to WARN, never raise."""
    r = _clean_results()
    for k in ("fnToStringSelf", "webglToString", "webgl2ToString",
              "deviceMemoryGetter", "uaDataGetter", "uaDataHenv"):
        del r[k]
    a = analyze_report(r)
    for k in ("fnToStringSelf", "webglToString", "webgl2ToString",
              "deviceMemoryGetter", "uaDataGetter", "uaDataHenv"):
        assert a["checks"][k]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_tostring_probe_errors_warn_not_crash():
    r = _clean_results()
    for k in ("fnToStringSelf", "webglToString", "webgl2ToString",
              "deviceMemoryGetter", "uaDataGetter", "uaDataHenv"):
        r[k] = "err:TypeError"
    a = analyze_report(r)
    for k in ("fnToStringSelf", "webglToString", "webgl2ToString",
              "deviceMemoryGetter", "uaDataGetter", "uaDataHenv"):
        assert a["checks"][k]["status"] == "WARN"


def test_device_memory_getter_absent_warns():
    """No own-property getter = the spoof never ran in this page."""
    r = _clean_results()
    r["deviceMemoryGetter"] = "no-own-prop"
    a = analyze_report(r)
    assert a["checks"]["deviceMemoryGetter"]["status"] == "WARN"
    assert a["summary"]["verdict"] == "attention"


def test_webgl_tostring_unavailable_warns():
    r = _clean_results()
    r["webglToString"] = "no-webgl1"
    r["webgl2ToString"] = "no-webgl2"
    a = analyze_report(r)
    assert a["checks"]["webglToString"]["status"] == "WARN"
    assert a["checks"]["webgl2ToString"]["status"] == "WARN"


def test_tostring_probes_clean_pass():
    a = analyze_report(_clean_results())
    assert a["checks"]["fnToStringSelf"]["status"] == "PASS"
    assert a["checks"]["webglToString"]["status"] == "PASS"
    assert a["checks"]["webgl2ToString"]["status"] == "PASS"
    assert a["checks"]["deviceMemoryGetter"]["status"] == "PASS"
    assert a["checks"]["uaDataGetter"]["status"] == "PASS"
    assert a["checks"]["uaDataHenv"]["status"] == "PASS"


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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_checks_js_regex_escapes_intact():
    """CHECKS embeds JS regexes — Python escape processing must not touch them.

    Regression: in a plain (non-raw) Python string \\b silently becomes a
    BACKSPACE character, which is a *legal* JS regex token that matches a
    literal backspace instead of a word boundary — corrupting the WebRTC
    private-IP detection so it never matched (leaks passed as clean).
    """
    assert "\x08" not in CHECKS
    assert "\\b(192" in CHECKS  # literal backslash-b in the private-IP regex
    assert "\\.local\\b" in CHECKS  # mDNS candidate filter too


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
      mimeTypes: {length: 2,
                  0: {type: 'application/pdf'}, 1: {type: 'text/pdf'}},
      mediaDevices: {enumerateDevices: async () =>
        [{kind: 'audioinput'}, {kind: 'audiooutput'}]},
    };
    const Notification = {permission: 'default'};
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
      if (!('webdriver' in r) || !('canvas' in r) || !('canvasIntegrity' in r)
          || !('permissions' in r)
          || !('iframeWebdriver' in r) || !('fonts' in r)
          || !('webgl2' in r) || !('webgl2Vendor' in r)
          || !('pluginNames' in r)
          || !('audioFingerprint' in r) || !('audioSampleRate' in r)
          || !('audioAllZeros' in r)
          || !('workerWebdriver' in r) || !('workerUserAgent' in r)
          || !('workerTimezoneOffset' in r) || !('workerTimezoneName' in r)
          || !('webdriverOwnProp' in r)
          || !('pluginsConstructor' in r) || !('mimeTypesConstructor' in r)
          || !('webrtcLeak' in r)
          || !('fnToStringSelf' in r) || !('webglToString' in r)
          || !('webgl2ToString' in r) || !('deviceMemoryGetter' in r)
          || !('uaDataGetter' in r) || !('uaDataHenv' in r)
          || !('notificationPermission' in r) || !('mimeTypes' in r)
          || !('mimeTypeNames' in r) || !('mediaDevices' in r)
          || !('tzDateOffsetName' in r) || !('tzIntlOffsetName' in r)
          || !('pdfViewerEnabled' in r)) {
        throw new Error('missing keys: ' + Object.keys(r));
      }
      if (r.permissions !== 'prompt') throw new Error('permissions: ' + r.permissions);
      if (r.notificationPermission !== 'default') {
        throw new Error('notificationPermission: ' + r.notificationPermission);
      }
      if (r.mimeTypes !== 2) throw new Error('mimeTypes: ' + r.mimeTypes);
      if (!Array.isArray(r.mimeTypeNames) || r.mimeTypeNames[0] !== 'application/pdf') {
        throw new Error('mimeTypeNames: ' + JSON.stringify(r.mimeTypeNames));
      }
      if (!r.mediaDevices || r.mediaDevices.count !== 2
          || r.mediaDevices.audioinput !== 1 || r.mediaDevices.audiooutput !== 1) {
        throw new Error('mediaDevices: ' + JSON.stringify(r.mediaDevices));
      }
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
