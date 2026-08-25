"""Anti-fingerprint verification: local JS checks + optional sannysoft scan.

The local checks exercise common bot-detection signals. With patchright +
the full Chromium build these should all behave like a real browser
(webdriver absent, plugins present, real UA, etc.). `analyze_report` turns
the raw captured values into a PASS/WARN/FAIL classification that the CLI
renders as a summary and persists as a JSON report.
"""

# JS checks executed in the page. This is an *async* IIFE so we can query
# `navigator.permissions` inside the same payload instead of a second round
# trip. With patchright + full Chromium the values should match a real
# Chrome 149 on Linux x86_64.
CHECKS = """
async () => {
  const r = {};
  r.webdriver = navigator.webdriver;
  r.languages = navigator.languages;
  r.plugins = navigator.plugins.length;
  r.chrome = !!window.chrome;
  r.chromeRuntime = !!(window.chrome && window.chrome.runtime && window.chrome.runtime.id !== undefined);
  r.userAgent = navigator.userAgent;
  r.platform = navigator.platform;
  r.hardwareConcurrency = navigator.hardwareConcurrency;
  r.deviceMemory = navigator.deviceMemory;
  r.maxTouchPoints = navigator.maxTouchPoints;
  r.devicePixelRatio = window.devicePixelRatio;
  r.viewportDelta = window.outerWidth - window.innerWidth;
  r.timezoneOffset = new Date().getTimezoneOffset();
  r.timezoneName = Intl.DateTimeFormat().resolvedOptions().timeZone;
  try {
    r.permissions = (await navigator.permissions.query({name: 'notifications'})).state;
  } catch (e) { r.permissions = 'err:' + e.name; }
  r.webglVendor = (() => {
    try {
      const c = document.createElement('canvas').getContext('webgl');
      const e = c.getExtension('WEBGL_debug_renderer_info');
      return e ? c.getParameter(e.UNMASKED_VENDOR_WEBGL) : 'no-ext';
    } catch (e) { return 'err'; }
  })();
  r.webgl = (() => {
    try {
      const c = document.createElement('canvas').getContext('webgl');
      const e = c.getExtension('WEBGL_debug_renderer_info');
      return e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'no-ext';
    } catch (e) { return 'err'; }
  })();
  r.canvas = (() => {
    // Cheap fingerprint of a canvas render — headless SwiftShader and real
    // GPU rasterize text slightly differently, which shows up as a hash
    // divergence between runs on the same machine.
    try {
      const c = document.createElement('canvas');
      c.width = 220; c.height = 30;
      const ctx = c.getContext('2d');
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#336699';
      ctx.fillText('stealth-browser fingerprint 1234567890', 2, 2);
      const url = c.toDataURL();
      let h = 5381;
      for (let i = 0; i < url.length; i++) h = ((h << 5) + h + url.charCodeAt(i)) >>> 0;
      return h.toString(16);
    } catch (e) { return 'err'; }
  })();
  return r;
}
"""

# Expected profile: Chrome 149 on Linux x86_64, deviceMemory=8 spoofed,
# WebGL spoofed to AMD Radeon, locale zh-CN, tz Asia/Shanghai (see browser.py).
EXPECTED = {
    "timezone_name": "Asia/Shanghai",
    "timezone_offset_min": -480,  # UTC+8
    "device_memory": 8,
}


def _status(name, results, good, note, bad="FAIL", missing="WARN"):
    """Classify one check: good -> PASS, anything else -> FAIL/WARN."""
    if name not in results or results[name] is None:
        return missing, f"missing (expected {note})"
    if good(results[name]):
        return "PASS", note
    return bad, note


def analyze_report(results: dict) -> dict:
    """Classify raw fingerprint results against the expected stealth profile.

    Pure Python — no browser needed, fully unit-testable. Returns::

        {
          "checks": {name: {"status", "expected", "actual", "note"}, ...},
          "summary": {"passed", "warned", "failed", "info", "verdict"},
        }

    status is one of PASS / WARN / FAIL / INFO.
    verdict is "clean" (no FAIL), "attention" (only WARNs) or "flagged".
    """
    checks = {}

    def add(name, status, note, expected="-"):
        checks[name] = {
            "status": status,
            "expected": expected,
            "actual": results.get(name, None),
            "note": note,
        }

    # -- hard failures: things a real Chrome never shows -------------------
    add("webdriver", "FAIL" if results.get("webdriver") else "PASS",
        "must be absent/undefined (patchright removes it)",
        "absent")
    if "HeadlessChrome" in str(results.get("userAgent", "")):
        add("userAgent", "FAIL", "HeadlessChrome leak in UA", "no 'HeadlessChrome'")
    else:
        add("userAgent", "PASS" if "Chrome/" in str(results.get("userAgent", ""))
            else "WARN", "real Chrome UA", "Chrome/1xx in UA")
    gl = str(results.get("webgl", ""))
    if "SwiftShader" in gl:
        add("webgl", "FAIL", "SwiftShader software renderer leak", "hardware GL")
    elif "AMD" in gl:
        add("webgl", "PASS", "hardware AMD renderer", "AMD Radeon")
    elif gl in ("err", "no-ext", "None", ""):
        add("webgl", "WARN", f"WebGL unavailable ({gl or 'empty'})", "AMD Radeon")
    else:
        add("webgl", "WARN", f"unexpected renderer: {gl}", "AMD Radeon")
    add("webglVendor", "PASS" if "AMD" in str(results.get("webglVendor", ""))
        else "WARN", "GPU vendor matches spoofed renderer", "Google Inc. (AMD)")

    # -- warnings: inconsistencies real browsers don't have -----------------
    add("plugins", "FAIL" if results.get("plugins", 0) == 0 else "PASS",
        "headless shell reports 0 plugins", ">= 1")
    add("permissions", "WARN" if str(results.get("permissions", "")).startswith("err")
        else ("PASS" if results.get("permissions") in ("prompt", "granted") else "WARN"),
        "query state should be prompt/granted", "prompt|granted")
    add("deviceMemory", "PASS" if results.get("deviceMemory") == EXPECTED["device_memory"]
        else "WARN", f"should be {EXPECTED['device_memory']} (spoofed)",
        str(EXPECTED["device_memory"]))
    add("hardwareConcurrency", "WARN" if results.get("hardwareConcurrency", 0) < 2
        else "PASS", "headless often reports 1", ">= 2")
    add("chromeRuntime", "WARN" if not results.get("chromeRuntime") else "PASS",
        "real Chrome exposes chrome.runtime", "present")
    tz = results.get("timezoneName")
    off = results.get("timezoneOffset")
    tz_ok = tz == EXPECTED["timezone_name"] and off == EXPECTED["timezone_offset_min"]
    add("timezone", "PASS" if tz_ok else "WARN",
        f"must be {EXPECTED['timezone_name']} (UTC+8, offset {EXPECTED['timezone_offset_min']})",
        f"{EXPECTED['timezone_name']} / {EXPECTED['timezone_offset_min']}")

    # -- informational: no single right answer, useful for spotting drift ---
    add("languages", "INFO", f"{results.get('languages')}", "zh-CN-ish")
    add("platform", "INFO", f"{results.get('platform')}", "Linux x86_64")
    add("maxTouchPoints", "INFO", "desktop should be 0",
        "0")
    add("devicePixelRatio", "INFO", "typically 1 on desktop",
        "1")
    add("viewportDelta", "INFO", "outer-inner; 0 in headless, >0 windowed",
        "> 0 windowed")
    add("canvas", "INFO", "render fingerprint hash; stable across runs",
        "stable hash")
    add("chrome", "INFO", f"window.chrome present: {bool(results.get('chrome'))}",
        "True")

    s = {"passed": 0, "warned": 0, "failed": 0, "info": 0}
    for c in checks.values():
        key = {"PASS": "passed", "WARN": "warned", "FAIL": "failed", "INFO": "info"}[c["status"]]
        s[key] += 1

    if s["failed"]:
        verdict = "flagged"
    elif s["warned"]:
        verdict = "attention"
    else:
        verdict = "clean"
    s["verdict"] = verdict
    return {"checks": checks, "summary": s}


async def sannysoft_scan(page) -> None:
    """Run the bot.sannysoft.com full detection suite and print the table.

    `page` must already be pointed at a page (we navigate inside).
    """
    await page.goto(
        "https://bot.sannysoft.com",
        timeout=30000,
        wait_until="domcontentloaded",
    )
    await page.wait_for_timeout(3000)
    rows = await page.evaluate(
        """() => {
            const out = {};
            document.querySelectorAll('table tr').forEach(tr => {
                const tds = tr.querySelectorAll('td');
                if (tds.length >= 2) {
                    const k = tds[0].innerText.trim();
                    const v = tds[1].innerText.trim();
                    if (k && v) out[k] = v;
                }
            });
            return out;
        }"""
    )
    print("TITLE:", await page.title())
    for k, v in rows.items():
        print(f"  {k}: {v}")
