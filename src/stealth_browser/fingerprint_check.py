"""Anti-fingerprint verification: local JS checks + optional sannysoft scan."""

# A set of JS checks that exercise common bot-detection signals. With
# patchright + the full Chromium build these should all behave like a real
# browser (webdriver absent, plugins present, etc.).
CHECKS = """
() => {
  const r = {};
  r.webdriver = navigator.webdriver;
  r.languages = navigator.languages;
  r.plugins = navigator.plugins.length;
  r.chrome = !!window.chrome;
  r.userAgent = navigator.userAgent;
  r.hardwareConcurrency = navigator.hardwareConcurrency;
  r.deviceMemory = navigator.deviceMemory;
  r.webgl = (() => {
    try {
      const c = document.createElement('canvas').getContext('webgl');
      const e = c.getExtension('WEBGL_debug_renderer_info');
      return e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'no-ext';
    } catch (e) { return 'err'; }
  })();
  return r;
}
"""


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
