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
# NOTE: raw string — the payload embeds JS regexes (\b, \d, \.). In a plain
# Python string \b silently becomes a BACKSPACE character (a legal JS regex
# token that matches a literal backspace instead of a word boundary), which
# corrupted the WebRTC private-IP detection so it never matched.
CHECKS = r"""
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
  // Notification.permission is the second surface of the same notification
  // permission: real Chrome always agrees (default ~ prompt, granted ~
  // granted, denied ~ denied). A spoof that patches only one surface — the
  // exact tell sannysoft's "Permissions" row catches — leaves the two
  // disagreeing.
  r.notificationPermission = (() => {
    try {
      return typeof Notification !== 'undefined' ? Notification.permission
                                                 : 'no-notification-api';
    } catch (e) { return 'err:' + e.name; }
  })();
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
  // MIME-type realism: Chrome's PDF plugins ship matching MIME types
  // (application/pdf, text/pdf). A length-only plugin spoof fabricates the
  // names but leaves navigator.mimeTypes empty — a known anti-spoof tell.
  r.mimeTypes = (() => {
    try { return navigator.mimeTypes.length; } catch (e) { return 'err:' + e.name; }
  })();
  r.mimeTypeNames = (() => {
    try { return Array.from(navigator.mimeTypes, (m) => m.type); }
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
  // AudioContext fingerprint: the third classic fingerprint surface after
  // canvas and WebGL. fingerprintjs/creepjs render an oscillator through a
  // DynamicsCompressor and hash the output; headless/soft-audio stacks
  // produce degenerate (all-zero) or missing results, and the sample rate
  // is a hardware-consistency signal. A spoof that patches canvas but not
  // WebAudio is a classic partial-spoof tell.
  r.audioSampleRate = null;
  r.audioAllZeros = false;
  r.audioFingerprint = await (async () => {
    try {
      const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      if (!Ctx) return 'no-audio';
      const actx = new Ctx(1, 44100, 44100);
      const osc = actx.createOscillator();
      osc.type = 'triangle';
      osc.frequency.value = 10000;
      const comp = actx.createDynamicsCompressor();
      comp.threshold.value = -50;
      comp.knee.value = 40;
      comp.ratio.value = 12;
      comp.attack.value = 0;
      comp.release.value = 0.25;
      osc.connect(comp);
      comp.connect(actx.destination);
      osc.start(0);
      const buf = await actx.startRendering();
      const ch = buf.getChannelData(0);
      let allZeros = true;
      let h = 5381;
      for (let i = 4500; i < 5000; i++) {
        if (ch[i] !== 0) allZeros = false;
        h = ((h << 5) + h + Math.round(ch[i] * 1e6)) >>> 0;
      }
      r.audioAllZeros = allZeros;
      r.audioSampleRate = actx.sampleRate;
      return h.toString(16);
    } catch (e) { return 'err:' + e.name; }
  })();
  // Web Worker context probe: anti-bot patches that only cover the main
  // world leak inside workers, where the page gets a fresh navigator.
  // fingerprintjs probes worker-scoped values for exactly this reason. We
  // check both webdriver and the UA string (a UA spoof that misses workers
  // leaks the headless UA there). Blob-URL workers work on any origin.
  r.workerWebdriver = null;
  r.workerUserAgent = null;
  await new Promise((resolve) => {
    try {
      if (typeof Worker === 'undefined') {
        r.workerWebdriver = 'no-worker';
        resolve();
        return;
      }
      const src = "postMessage({wd: navigator.webdriver, ua: navigator.userAgent});";
      const url = URL.createObjectURL(new Blob([src], {type: 'application/javascript'}));
      const w = new Worker(url);
      let done = false;
      const finish = (wd, ua) => {
        if (done) return;
        done = true;
        try { w.terminate(); } catch (e) {}
        try { URL.revokeObjectURL(url); } catch (e) {}
        r.workerWebdriver = wd === undefined ? null : String(wd);
        r.workerUserAgent = ua === undefined ? null : String(ua);
        resolve();
      };
      w.onmessage = (ev) => {
        try {
          const d = ev.data || {};
          finish(d.wd, d.ua);
        } catch (e) {
          if (!done) { r.workerWebdriver = 'err:' + e.name; finish(); }
        }
      };
      w.onerror = () => { if (!done) r.workerWebdriver = 'err:worker'; finish(); };
      setTimeout(() => {
        if (!done && r.workerWebdriver === null) r.workerWebdriver = 'timeout';
        finish();
      }, 1500);
    } catch (e) {
      r.workerWebdriver = 'err:' + e.name;
      resolve();
    }
  });
  // Media device enumeration: fingerprintjs probes enumerateDevices — real
  // desktop Chrome always exposes at least one audio output, while headless
  // shells report an empty list. Bucket counts only (never device IDs) so
  // the JSON report stays safe to share.
  r.mediaDevices = await (async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
        return 'no-media-devices';
      }
      const devs = await navigator.mediaDevices.enumerateDevices();
      const out = {count: devs.length, audioinput: 0, audiooutput: 0, videoinput: 0};
      for (const d of devs) {
        if (out[d.kind] !== undefined) out[d.kind]++;
      }
      return out;
    } catch (e) { return 'err:' + e.name; }
  })();
  // WebRTC leak probe: a data-channel peer connection gathers ICE candidates
  // even with no remote peer. Chrome's privacy default hides local IPs
  // behind mDNS (.local) hostnames; raw RFC1918 IPs in host candidates mean
  // the real machine IP is exposed to page scripts — behind a proxy that is
  // an IP-consistency leak anti-bot systems actively probe for. We report
  // bucket counts only (never raw candidate strings) so the JSON report
  // stays safe to share.
  r.webrtcLeak = await new Promise((resolve) => {
    try {
      if (typeof RTCPeerConnection === 'undefined') {
        resolve({status: 'no-webrtc'});
        return;
      }
      const pc = new RTCPeerConnection({});
      const found = [];
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        try { pc.close(); } catch (e) {}
        let mdns = 0, privateIp = 0, publicIp = 0, other = 0;
        const rePrivate = /\b(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+)\b/;
        for (const c of found) {
          if (/\.local\b/.test(c)) mdns++;
          else if (rePrivate.test(c)) privateIp++;
          else if (/typ srflx|typ prflx|typ relay/.test(c)) publicIp++;
          else other++;
        }
        resolve({status: 'done', mdns, privateIp, publicIp, other, total: found.length});
      };
      pc.createDataChannel('probe');
      pc.onicecandidate = (ev) => {
        if (done) return;
        try {
          if (!ev.candidate) finish();
          else found.push(String(ev.candidate.candidate || ''));
        } catch (e) { found.push('parse-err'); }
      };
      pc.createOffer().then((o) => pc.setLocalDescription(o)).catch(() => {});
      setTimeout(finish, 2000);
    } catch (e) { resolve({status: 'err:' + e.name}); }
  });
  // -- native toString consistency -----------------------------------------
  // Anti-bot libraries call Function.prototype.toString on native-looking
  // methods to expose spoofs: a patched WebGL getParameter whose source
  // still contains the hardcoded vendor constants is an instant tell.
  // browser.py registers every injected function with a toString shim;
  // these probes verify the shim holds — and that the shim itself stays
  // invisible (a toString whose own source leaks is worse than no shim).
  r.fnToStringSelf = (() => {
    try { return Function.prototype.toString.toString(); }
    catch (e) { return 'err:' + e.name; }
  })();
  r.webglToString = (() => {
    try {
      if (typeof WebGLRenderingContext === 'undefined') return 'no-webgl1';
      return WebGLRenderingContext.prototype.getParameter.toString();
    } catch (e) { return 'err:' + e.name; }
  })();
  r.webgl2ToString = (() => {
    try {
      if (typeof WebGL2RenderingContext === 'undefined') return 'no-webgl2';
      return WebGL2RenderingContext.prototype.getParameter.toString();
    } catch (e) { return 'err:' + e.name; }
  })();
  r.deviceMemoryGetter = (() => {
    try {
      const d = Object.getOwnPropertyDescriptor(navigator, 'deviceMemory');
      if (!d) return 'no-own-prop';
      return d.get ? d.get.toString() : 'own-no-getter';
    } catch (e) { return 'err:' + e.name; }
  })();
  r.uaDataGetter = (() => {
    try {
      const d = Object.getOwnPropertyDescriptor(navigator, 'userAgentData');
      if (!d) return 'no-own-prop';
      return d.get ? d.get.toString() : 'own-no-getter';
    } catch (e) { return 'err:' + e.name; }
  })();
  r.uaDataHenv = (() => {
    try {
      const h = navigator.userAgentData
        && navigator.userAgentData.getHighEntropyValues;
      return h ? h.toString() : 'no-henv';
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

# Marker strings that must never appear in a native-looking toString()
# result: the WebGL vendor-id constant, the spoofed renderer, arrow getters
# and the toString shim itself (its source references the spoof registry).
_TOAST_LEAK_MARKERS = ("37445", "AMD Radeon", "=>", "spoof")


def _native_leak(s) -> bool:
    """True when a toString() result leaks JS source instead of native code.

    Native methods stringify to ``function <name>() { [native code] }``; a
    spoof whose source survives the probe contains its own code — and often
    the spoof constants themselves (see _TOAST_LEAK_MARKERS).
    """
    s = str(s)
    if "[native code]" not in s:
        return True
    return any(m in s for m in _TOAST_LEAK_MARKERS)


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

    # -- extended surface probes: audio fingerprint, worker context, WebRTC -
    # Audio fingerprint: WebAudio is the third classic fingerprint surface
    # (canvas, WebGL, audio). Degenerate (all-zero) renders or a missing
    # WebAudio stack are bot signals; the hash itself is informational.
    afp = results.get("audioFingerprint")
    if afp is None:
        add("audioFingerprint", "WARN", "audio fingerprint unavailable (missing)",
            "non-degenerate render")
    elif str(afp) == "no-audio" or str(afp).startswith("err:"):
        add("audioFingerprint", "WARN", f"WebAudio unavailable ({afp})",
            "non-degenerate render")
    elif results.get("audioAllZeros"):
        add("audioFingerprint", "FAIL",
            "audio render is all-zero — degenerate/soft audio stack",
            "non-degenerate render")
    else:
        add("audioFingerprint", "PASS", f"audio fingerprint captured ({afp})",
            "non-degenerate render")
    sr = results.get("audioSampleRate")
    if sr in (44100, 48000):
        add("audioSampleRate", "PASS", f"sample rate {sr} Hz (typical desktop)",
            "44100|48000")
    elif sr is None:
        add("audioSampleRate", "WARN", "sample rate unavailable", "44100|48000")
    else:
        add("audioSampleRate", "WARN", f"unusual sample rate {sr} Hz", "44100|48000")
    # Worker context: patches that only cover the main world leak inside
    # Web Workers (a fresh navigator object). Same None-is-clean convention
    # as the iframe webdriver check (verified absence, not missing data).
    wwd = results.get("workerWebdriver")
    if wwd is None or str(wwd).lower() == "false":
        add("workerWebdriver", "PASS", "webdriver absent inside Web Workers too", "absent")
    elif wwd is True or str(wwd).lower() == "true":
        add("workerWebdriver", "FAIL", f"worker leaks webdriver={wwd}", "absent")
    else:
        add("workerWebdriver", "WARN", f"cannot verify worker webdriver ({wwd})", "absent")
    # Workers always share the creating document's UA — a mismatch means a
    # UA spoof that does not cover the worker scope (headless UA leak).
    wua = results.get("workerUserAgent")
    mua = str(results.get("userAgent", ""))
    if wua is None:
        add("workerUserAgent", "WARN", "worker UA unavailable", "matches main frame UA")
    elif str(wua) == mua:
        add("workerUserAgent", "PASS", "worker UA matches the main frame", "matches main frame UA")
    else:
        add("workerUserAgent", "FAIL",
            f"worker UA differs from main frame — worker-scope spoof leak ({str(wua)[:60]})",
            "matches main frame UA")
    # WebRTC: raw local IPs in ICE candidates are an IP-consistency leak
    # (the real machine IP readable by page scripts, e.g. behind a proxy).
    wrtc = results.get("webrtcLeak")
    if wrtc is None:
        add("webrtcLeak", "WARN", "WebRTC probe unavailable (missing)", "no raw local IPs")
    elif not isinstance(wrtc, dict):
        add("webrtcLeak", "WARN", f"WebRTC probe result unreadable ({wrtc})", "no raw local IPs")
    elif str(wrtc.get("status", "")).startswith("err"):
        add("webrtcLeak", "WARN", f"WebRTC probe failed ({wrtc.get('status')})", "no raw local IPs")
    elif wrtc.get("status") == "no-webrtc":
        add("webrtcLeak", "WARN", "RTCPeerConnection missing — unusual for real Chrome",
            "present but protected")
    elif wrtc.get("privateIp", 0):
        add("webrtcLeak", "FAIL",
            f"{wrtc.get('privateIp')} raw private IP(s) in ICE candidates — "
            "local IP exposed to page scripts",
            "mDNS-obfuscated or no local candidates")
    else:
        add("webrtcLeak", "PASS",
            f"no raw local IPs leaked ({wrtc.get('mdns', 0)} mDNS, "
            f"{wrtc.get('publicIp', 0)} reflexive, {wrtc.get('other', 0)} other)",
            "no raw local IPs")
    # Media device enumeration: real desktop Chrome always exposes at least
    # one audio output device; headless shells report an empty list
    # (fingerprintjs probes this surface). Counts only — never device IDs.
    md = results.get("mediaDevices")
    if md is None:
        add("mediaDevices", "WARN", "media device probe unavailable (missing)",
            ">= 1 device")
    elif not isinstance(md, dict):
        add("mediaDevices", "WARN", f"media device probe failed ({md})",
            ">= 1 device")
    elif md.get("count"):
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(md.items())
                          if k != "count" and v)
        add("mediaDevices", "PASS", f"{md['count']} media device(s) ({kinds})",
            ">= 1 device")
    else:
        add("mediaDevices", "WARN", "no media devices — headless shells report none",
            ">= 1 device")

    # -- native toString consistency (spoof-source leaks) -------------------
    # Anti-bot libraries call Function.prototype.toString on native-looking
    # methods to expose spoofs. browser.py registers every injected function
    # with a toString shim; these checks verify the shim holds — and that
    # the shim itself stays invisible (a leaking toString shim is worse
    # than no shim at all).
    fts = results.get("fnToStringSelf")
    if fts is None or str(fts).startswith("err:"):
        add("fnToStringSelf", "WARN",
            f"Function.prototype.toString probe unavailable ({fts})",
            "function toString() { [native code] }")
    elif _native_leak(fts):
        add("fnToStringSelf", "FAIL",
            f"toString shim leaks its own source: {str(fts)[:60]}",
            "function toString() { [native code] }")
    else:
        add("fnToStringSelf", "PASS", "Function.prototype.toString looks native",
            "function toString() { [native code] }")
    for key, label, missing in (
            ("webglToString", "WebGL1", "no-webgl1"),
            ("webgl2ToString", "WebGL2", "no-webgl2")):
        s = results.get(key)
        sv = str(s) if s is not None else ""
        if s is None or sv in (missing,) or sv.startswith("err:"):
            add(key, "WARN", f"{label} getParameter.toString unavailable ({s})",
                "function getParameter() { [native code] }")
        elif _native_leak(sv):
            add(key, "FAIL",
                f"{label} getParameter leaks spoof source via toString: "
                f"{sv[:60]}",
                "function getParameter() { [native code] }")
        else:
            add(key, "PASS", f"{label} getParameter survives toString probing",
                "function getParameter() { [native code] }")
    for key, label in (("deviceMemoryGetter", "deviceMemory"),
                       ("uaDataGetter", "userAgentData")):
        s = results.get(key)
        sv = str(s) if s is not None else ""
        if s is None or sv.startswith("err:"):
            add(key, "WARN", f"{label} getter probe unavailable ({s})",
                "native-looking getter")
        elif sv == "no-own-prop":
            add(key, "WARN",
                f"{label} own-property spoof missing "
                "(apply_stealth not run in this page?)",
                "spoofed own-property getter")
        elif sv == "own-no-getter":
            add(key, "WARN", f"{label} spoofed as data property (no getter)",
                "spoofed own-property getter")
        elif _native_leak(sv):
            add(key, "FAIL",
                f"{label} getter leaks its source via toString: {sv[:60]}",
                "native-looking getter")
        else:
            add(key, "PASS", f"{label} getter survives toString probing",
                "native-looking getter")
    henv = results.get("uaDataHenv")
    hv = str(henv) if henv is not None else ""
    if henv is None or hv in ("no-henv",) or hv.startswith("err:"):
        add("uaDataHenv", "WARN",
            f"getHighEntropyValues probe unavailable ({henv})",
            "native-looking method")
    elif _native_leak(hv):
        add("uaDataHenv", "FAIL",
            f"getHighEntropyValues leaks the UA-CH spoof source: {hv[:60]}",
            "native-looking method")
    else:
        add("uaDataHenv", "PASS", "getHighEntropyValues survives toString probing",
            "native-looking method")

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
    # MIME-type realism: Chrome's PDF plugins ship matching MIME types
    # (application/pdf, text/pdf). A length-only plugin spoof fabricates the
    # names but leaves navigator.mimeTypes empty — a known anti-spoof tell.
    mt = results.get("mimeTypes")
    mtn = results.get("mimeTypeNames")
    if mt is None and mtn is None:
        add("mimeTypes", "WARN", "mimeTypes unavailable (missing)",
            "PDF mime types present")
    elif isinstance(mtn, list) and mtn:
        joined = ", ".join(str(t) for t in mtn)
        if any("pdf" in str(t).lower() for t in mtn):
            add("mimeTypes", "PASS",
                f"mime types include the PDF handlers ({joined[:70]})",
                "PDF mime types present")
        else:
            add("mimeTypes", "WARN",
                f"{len(mtn)} mime types, none is a PDF handler — fabricated plugin list",
                "PDF mime types present")
    elif (mt == 0 or mtn == []) and results.get("plugins", 0):
        add("mimeTypes", "WARN",
            "plugins present but navigator.mimeTypes is empty — length-only plugin spoof",
            "PDF mime types present")
    elif mt == 0 or mtn == []:
        add("mimeTypes", "WARN", "no mime types at all (headless-shell profile)",
            "PDF mime types present")
    elif str(mt).startswith("err:") and (mtn is None or str(mtn).startswith("err:")):
        add("mimeTypes", "WARN", f"mimeTypes probe failed ({mt})",
            "PDF mime types present")
    else:
        add("mimeTypes", "PASS", f"navigator.mimeTypes reports {mt} entries",
            "PDF mime types present")
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
    # Permission-surface cross-check: navigator.permissions.query and
    # Notification.permission expose the same underlying notification
    # permission. Real Chrome always agrees (default ~ prompt, granted ~
    # granted, denied ~ denied); a spoof that patches only one surface — the
    # exact tell sannysoft's "Permissions" row catches — leaves them
    # disagreeing. One surface missing/erroneous means we cannot cross-check
    # (WARN); readable surfaces that disagree are a hard FAIL.
    notif = results.get("notificationPermission")
    perm = str(results.get("permissions", ""))
    neutral = ("default", "prompt")
    if notif is None or str(notif) in ("no-notification-api",) or str(notif).startswith("err:"):
        add("notificationPermission", "WARN",
            f"Notification.permission unavailable ({notif})",
            "consistent with permissions.query")
    elif perm.startswith("err:") or not perm:
        add("notificationPermission", "WARN",
            f"cannot cross-check (permissions.query unavailable: {perm or 'missing'})",
            "consistent with permissions.query")
    elif str(notif) == perm or (str(notif) in neutral and perm in neutral):
        add("notificationPermission", "PASS",
            f"Notification.permission ({notif}) agrees with permissions.query ({perm})",
            "consistent with permissions.query")
    else:
        add("notificationPermission", "FAIL",
            f"permission surfaces disagree: Notification.permission={notif} "
            f"but permissions.query={perm} — partial-spoof tell",
            "consistent with permissions.query")
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
