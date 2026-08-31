"""Anti-fingerprint verification: local JS checks + optional sannysoft scan.

The local checks exercise common bot-detection signals. With patchright +
the full Chromium build these should all behave like a real browser
(webdriver absent, plugins present, real UA, etc.). `analyze_report` turns
the raw captured values into a PASS/WARN/FAIL classification that the CLI
renders as a summary and persists as a JSON report.
"""

import re

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
  // Legacy navigator members: headless Chrome leaks 'HeadlessChrome' here
  // even when the UA string itself is patched (fingerprintjs & creepjs probe
  // these separately from userAgent). A robust spoof keeps them consistent.
  r.appVersion = navigator.appVersion;
  r.appCodeName = navigator.appCodeName;
  r.product = navigator.product;
  r.productSub = navigator.productSub;
  r.vendor = navigator.vendor;
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
  r.webgl2 = (() => {
    // WebGL2 must report the SAME renderer as WebGL1: modern Chrome always
    // ships WebGL2 and both contexts expose the same hardware. A spoof that
    // only patches WebGLRenderingContext.prototype leaks the real (often
    // SwiftShader) renderer through the WebGL2 context — a classic
    // partial-spoof tell (fingerprintjs and creepjs probe both contexts).
    try {
      const c = document.createElement('canvas').getContext('webgl2');
      if (!c) return 'no-webgl2';
      const e = c.getExtension('WEBGL_debug_renderer_info');
      return e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'no-ext';
    } catch (e) { return 'err'; }
  })();
  r.webgl2Vendor = (() => {
    try {
      const c = document.createElement('canvas').getContext('webgl2');
      if (!c) return 'no-webgl2';
      const e = c.getExtension('WEBGL_debug_renderer_info');
      return e ? c.getParameter(e.UNMASKED_VENDOR_WEBGL) : 'no-ext';
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
  // -- extended surface checks ---------------------------------------------
  // webdriver inside a same-origin about:blank iframe: stealth patches that
  // only cover the top frame (or init scripts stuck in an isolated world)
  // leak here even when the main frame looks clean. A real detection
  // technique — sannysoft and creepjs both test nested frames.
  r.iframeWebdriver = await new Promise((resolve) => {
    try {
      if (!document.body) { resolve('nobody'); return; }
      const f = document.createElement('iframe');
      let done = false;
      const finish = (v) => {
        if (done) return;
        done = true;
        try { f.remove(); } catch (e) {}
        resolve(v);
      };
      f.onload = () => {
        try {
          const w = f.contentWindow;
          finish(w && w.navigator && w.navigator.webdriver !== undefined
            ? String(w.navigator.webdriver) : null);
        } catch (e) { finish('err:' + e.name); }
      };
      try {
        f.style.display = 'none';
        document.body.appendChild(f);
      } catch (e) { finish('err:' + e.name); return; }
      // about:blank frames are usually ready synchronously; the timer only
      // covers engines that fire onload late (finish() is idempotent).
      setTimeout(() => { try { if (f.onload) f.onload(); } catch (e) { finish('err:timeout'); } }, 50);
    } catch (e) { resolve('err:' + e.name); }
  });
  // Plugin-name realism: every desktop Chrome ships its PDF viewers inside
  // navigator.plugins. An array with the right *length* but fabricated names
  // (a length-only spoof) is a known anti-spoof tell.
  r.pluginNames = (() => {
    try { return Array.from(navigator.plugins, (p) => p.name); }
    catch (e) { return 'err:' + e.name; }
  })();
  // Standard font availability: minimal bot containers ship no fonts, real
  // desktops have Arial/Times/etc (Linux maps them via fontconfig). Metric
  // based detection (same idea as fingerprintjs): the probe font is
  // installed only if the width differs from BOTH generic baselines.
  r.fonts = (() => {
    try {
      const c = document.createElement('canvas');
      const ctx = c.getContext && c.getContext('2d');
      if (!ctx) return 'err:no-2d';
      const text = 'mmmmmmmmmmlli Ww@#0123 ';
      const measure = (font) => { ctx.font = '72px ' + font; return ctx.measureText(text).width; };
      const baseMono = measure('monospace');
      const baseSerif = measure('serif');
      const out = {};
      for (const f of ['Arial', 'Times New Roman', 'Courier New', 'Verdana', 'Georgia']) {
        const a = measure(f + ', monospace');
        const b = measure(f + ', serif');
        out[f] = (a !== baseMono) && (b !== baseSerif);
      }
      return out;
    } catch (e) { return 'err:' + e.name; }
  })();
  try {
    r.screenWidth = screen.width;
    r.screenHeight = screen.height;
    r.screenColorDepth = screen.colorDepth;
  } catch (e) {
    r.screenWidth = null; r.screenHeight = null; r.screenColorDepth = null;
  }
  r.chromeCsi = !!(window.chrome && window.chrome.csi);
  r.chromeLoadTimes = !!(window.chrome && window.chrome.loadTimes);
  // UA-CH (client hints): what the page sees must be consistent with the UA
  // string we advertise. Guarded — older engines without userAgentData just
  // report nulls and the analyzer treats them as missing.
  const uad = navigator.userAgentData;
  r.uaDataBrands = uad ? JSON.stringify(uad.brands) : null;
  r.uaDataMobile = uad ? uad.mobile : null;
  r.uaDataPlatform = uad ? uad.platform : null;
  if (uad && uad.getHighEntropyValues) {
    try {
      const he = await uad.getHighEntropyValues(
        ['uaFullVersion', 'fullVersionList', 'architecture', 'bitness', 'wow64']);
      r.uaFullVersion = he.uaFullVersion;
    } catch (e) { r.uaFullVersion = 'err:' + e.name; }
  } else {
    r.uaFullVersion = null;
  }
  return r;
}
"""

# Expected profile: Chrome 149 on Linux x86_64, deviceMemory=8 spoofed,
# WebGL spoofed to AMD Radeon, locale zh-CN, tz Asia/Shanghai (see browser.py).
EXPECTED = {
    "timezone_name": "Asia/Shanghai",
    "timezone_offset_min": -480,  # UTC+8
    "device_memory": 8,
    "locale": "zh-CN",
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
    # webdriver inside an about:blank iframe — patches that only cover the
    # top frame leak here even when the main frame looks clean.
    ifw = results.get("iframeWebdriver")
    if ifw is None or ifw is False or str(ifw).lower() == "false":
        add("iframeWebdriver", "PASS", "webdriver absent inside iframe too", "absent")
    elif ifw is True or str(ifw).lower() == "true":
        add("iframeWebdriver", "FAIL", f"iframe leaks webdriver={ifw}", "absent")
    else:
        add("iframeWebdriver", "WARN", f"cannot verify iframe webdriver ({ifw})", "absent")
    if "HeadlessChrome" in str(results.get("userAgent", "")):
        add("userAgent", "FAIL", "HeadlessChrome leak in UA", "no 'HeadlessChrome'")
    else:
        add("userAgent", "PASS" if "Chrome/" in str(results.get("userAgent", ""))
            else "WARN", "real Chrome UA", "Chrome/1xx in UA")
    # Legacy navigator consistency: headless Chrome leaks 'HeadlessChrome'
    # in appVersion (and a tell-tale '' vendor) even when the UA string alone
    # is patched. fingerprintjs/creepjs read these members independent of the
    # userAgent string, so they must agree with the Chrome UA we advertise.
    av = str(results.get("appVersion", ""))
    if "HeadlessChrome" in av or "Headless" in av:
        add("appVersion", "FAIL", f"HeadlessChrome leak in navigator.appVersion: {av[:60]}",
            "no 'Headless'")
    elif "Chrome/" in av:
        add("appVersion", "PASS", "appVersion matches a real Chrome build",
            "Chrome/1xx in appVersion")
    else:
        add("appVersion", "WARN", f"appVersion lacks a Chrome build token: {av[:60]}",
            "Chrome/1xx in appVersion")
    # appCodeName/product/productSub/vendor must be the standard web-constant
    # values a real Chromium ships. Headless spoofs that only patch
    # navigator.userAgent leave these at their default (or their real) values.
    acn = str(results.get("appCodeName", ""))
    add("appCodeName", "PASS" if acn == "Mozilla" else "WARN",
        f"appCodeName = {acn or 'empty'}", "Mozilla")
    prod = str(results.get("product", ""))
    add("product", "PASS" if prod == "Gecko" else "WARN",
        f"product = {prod or 'empty'}", "Gecko")
    prodsub = str(results.get("productSub", ""))
    # Real Chrome reports '20030107'; missing/null is a headless tell.
    if prodsub in ("", "None", "null", "undefined", "0"):
        add("productSub", "WARN", f"productSub missing/empty ({prodsub})", "20030107")
    elif prodsub == "20030107":
        add("productSub", "PASS", "productSub matches real Chrome", "20030107")
    else:
        add("productSub", "WARN", f"unexpected productSub ({prodsub})", "20030107")
    vend = str(results.get("vendor", ""))
    if "HeadlessChrome" in vend or vend == "":
        add("vendor", "FAIL" if "Headless" in vend else "WARN",
            f"navigator.vendor = {vend or 'empty'}", "Google Inc.")
    elif vend == "Google Inc.":
        add("vendor", "PASS", "vendor matches Google Inc.", "Google Inc.")
    else:
        add("vendor", "WARN", f"unexpected vendor ({vend})", "Google Inc.")
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
    # WebGL2 must agree with WebGL1: modern Chrome always ships WebGL2, and
    # both contexts expose the same hardware renderer. A spoof that only
    # patches WebGLRenderingContext.prototype leaks the real (often
    # SwiftShader) renderer through the WebGL2 context — a classic
    # partial-spoof tell. This check also proves OUR spoof covers both
    # prototypes (browser.py patches WebGLRenderingContext.prototype AND
    # WebGL2RenderingContext.prototype).
    gl1 = str(results.get("webgl", ""))
    gl2 = str(results.get("webgl2", ""))
    if gl2 in ("", "no-webgl2", "no-ext", "err"):
        add("webgl2", "WARN",
            f"WebGL2 unavailable ({gl2 or 'empty'}) — modern Chrome always ships it",
            "same renderer as WebGL1")
    elif "SwiftShader" in gl2:
        add("webgl2", "FAIL", "SwiftShader leaks via WebGL2 (WebGL1-only spoof)",
            "hardware GL")
    elif "AMD" in gl1 and "AMD" not in gl2:
        add("webgl2", "FAIL",
            f"WebGL2 renderer '{gl2[:60]}' doesn't match spoofed WebGL1 — partial spoof leak",
            "AMD Radeon (consistent with WebGL1)")
    elif "AMD" in gl2:
        add("webgl2", "PASS", "WebGL2 renderer matches the spoofed WebGL1 profile",
            "AMD Radeon")
    else:
        add("webgl2", "WARN", f"unexpected WebGL2 renderer: {gl2[:60]}", "AMD Radeon")
    gv2 = str(results.get("webgl2Vendor", ""))
    if gv2 and gv2 not in ("no-webgl2", "no-ext", "err"):
        add("webgl2Vendor", "PASS" if "AMD" in gv2 else "WARN",
            "GPU vendor consistent on the WebGL2 context too", "Google Inc. (AMD)")
    else:
        add("webgl2Vendor", "WARN", f"WebGL2 vendor unavailable ({gv2 or 'empty'})",
            "Google Inc. (AMD)")

    # -- client hints (UA-CH): modern anti-bot checks these for consistency --
    # Real Chrome advertises a "Google Chrome" brand in navigator.userAgentData;
    # headless builds report only "Chromium", a strong bot signal on its own.
    ua_brands = results.get("uaDataBrands")
    if ua_brands is None:
        add("uaChBrands", "FAIL", "client hints unavailable (userAgentData missing)",
            "Google Chrome + Chromium")
    elif "Google Chrome" not in str(ua_brands):
        add("uaChBrands", "FAIL", f"no 'Google Chrome' brand in {ua_brands}",
            "Google Chrome + Chromium")
    else:
        add("uaChBrands", "PASS", "brands include Google Chrome",
            "Google Chrome + Chromium")
    # uaFullVersion must equal the full version in the UA string (headless
    # builds leak a stale build number, e.g. .0 vs the UA's .55).
    ua_m = re.search(r"Chrome/(\d+\.\d+\.\d+\.\d+)",
                     str(results.get("userAgent", "")))
    full = results.get("uaFullVersion")
    if ua_m and full and not str(full).startswith("err:"):
        add("uaChVersion", "PASS" if ua_m.group(1) == str(full) else "FAIL",
            f"uaFullVersion {full} vs UA {ua_m.group(1)}", ua_m.group(1))
    else:
        add("uaChVersion", "WARN", "cannot compare (UA or uaFullVersion missing)",
            "match UA full version")
    # The client-hints platform must agree with the OS the UA claims.
    ua = str(results.get("userAgent", ""))
    ua_plat = ("Windows" if "Windows" in ua
               else "Mac" if "Macintosh" in ua
               else "Linux" if "Linux" in ua else "")
    uad_plat = str(results.get("uaDataPlatform", ""))
    plat_map = {"Linux": "Linux", "Windows": "Windows", "Mac": "macOS"}
    if ua_plat and uad_plat and uad_plat in plat_map.values():
        add("uaChPlatform", "PASS" if plat_map[ua_plat] == uad_plat else "FAIL",
            f"client-hints platform {uad_plat} vs UA {ua_plat}", plat_map[ua_plat])
    else:
        add("uaChPlatform", "WARN", "cannot compare (missing uaDataPlatform)",
            "match UA OS")
    mobile = results.get("uaDataMobile")
    add("uaChMobile", "PASS" if mobile is False else "WARN",
        "desktop profile must not claim mobile", "false")

    # -- warnings: inconsistencies real browsers don't have -----------------
    add("plugins", "FAIL" if results.get("plugins", 0) == 0 else "PASS",
        "headless shell reports 0 plugins", ">= 1")
    # Plugin-name realism: real desktop Chrome always lists its PDF viewers
    # (Chrome 149 reports 5 entries, all "…PDF Viewer" variants). A spoofed
    # array of the right length with fabricated names is a known anti-spoof
    # check — length alone is not enough.
    names = results.get("pluginNames")
    if isinstance(names, list) and names:
        joined = ", ".join(str(n) for n in names)
        if "PDF" in joined:
            add("pluginNames", "PASS",
                f"plugins include the PDF viewers Chrome ships ({joined[:70]})",
                "Chrome PDF plugins present")
        else:
            add("pluginNames", "WARN",
                f"{len(names)} plugins, none is a PDF viewer — fabricated plugin list",
                "Chrome PDF plugins present")
    elif isinstance(names, list):
        add("pluginNames", "WARN", "empty plugin list (see plugins check)",
            "Chrome PDF plugins present")
    else:
        add("pluginNames", "WARN", f"cannot read plugin names ({names})",
            "Chrome PDF plugins present")
    fonts = results.get("fonts")
    if isinstance(fonts, dict) and fonts:
        avail = sum(1 for v in fonts.values() if v)
        total = len(fonts)
        if avail == 0:
            add("fonts", "FAIL", f"no standard fonts installed (0/{total}) — minimal container",
                ">= 1 of the common desktop fonts")
        elif avail < total:
            add("fonts", "WARN", f"some standard fonts missing ({avail}/{total})",
                "all common desktop fonts")
        else:
            add("fonts", "PASS", f"standard fonts present ({avail}/{total})",
                "all common desktop fonts")
    else:
        add("fonts", "WARN", f"cannot probe fonts ({fonts})", "all common desktop fonts")
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
    # locale/languages consistency: anti-bot systems cross-check the HTTP
    # Accept-Language header against navigator.languages — a mismatch is a
    # classic misconfigured-spoof tell.
    langs = results.get("languages")
    if isinstance(langs, (list, tuple)) and langs:
        first = str(langs[0]).lower()
        add("languages",
            "PASS" if first.startswith(EXPECTED["locale"][:2].lower()) else "WARN",
            f"languages[0]={langs[0]} must match locale {EXPECTED['locale']}",
            f"{EXPECTED['locale']} first")
    else:
        add("languages", "WARN", f"navigator.languages unavailable ({langs})",
            f"{EXPECTED['locale']} first")
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
    sw, sh = results.get("screenWidth"), results.get("screenHeight")
    if isinstance(sw, int) and isinstance(sh, int) and sw > 0 and sh > 0:
        plausible = sw >= 1024 and sh >= 700
        checks["screenSize"] = {
            "status": "INFO" if plausible else "WARN",
            "expected": ">= 1024x700",
            "actual": f"{sw}x{sh}",
            "note": (f"screen {sw}x{sh}" if plausible else
                     f"screen {sw}x{sh} — suspiciously small (headless default is 800x600)"),
        }
    else:
        add("screenSize", "WARN", f"screen size unavailable ({sw}x{sh})", ">= 1024x700")
    add("chromeCsi", "INFO", f"chrome.csi present: {bool(results.get('chromeCsi'))}",
        "True on real Chrome")
    add("chromeLoadTimes", "INFO",
        f"chrome.loadTimes present: {bool(results.get('chromeLoadTimes'))}",
        "True on real Chrome")

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
