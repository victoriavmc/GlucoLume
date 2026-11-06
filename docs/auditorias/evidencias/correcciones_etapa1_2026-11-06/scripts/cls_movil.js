const { chromium } = require('playwright');
const DIST = process.env.DIST_INDEX; const BASE = process.env.BASE;
(async () => {
  const b = await chromium.launch(); const out = [];
  for (let rep = 1; rep <= 3; rep++) {
    const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
    await ctx.route(/\/ayuda\/?(\?.*)?$/, (r) => (r.request().resourceType() === 'document' ? r.fulfill({ path: DIST, contentType: 'text/html' }) : r.continue()));
    const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p); await cdp.send('Performance.enable');
    p.on('crash', () => out.push('CRASH rep ' + rep)); p.on('pageerror', (e) => out.push('pageerror ' + String(e).slice(0, 120)));
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
    await p.addInitScript(() => { window.__cls = []; new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__cls.push({ v: e.value, input: e.hadRecentInput }))).observe({ type: 'layout-shift', buffered: true }); });
    await p.goto(BASE + '/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
    await p.waitForTimeout(300);
    for (let i = 0; i < 60; i++) { await p.evaluate(() => window.scrollBy(0, 200)); await p.waitForTimeout(120); }
    await p.waitForTimeout(1500);
    const shifts = await p.evaluate(() => window.__cls).catch((e) => 'ERR ' + e.message.slice(0, 80));
    out.push({ rep, shifts: typeof shifts === 'string' ? shifts : { cls: +shifts.filter((s) => !s.input).reduce((a, s) => a + s.v, 0).toFixed(4), n: shifts.filter((s) => !s.input).length } });
    await ctx.close();
  }
  console.log(JSON.stringify(out)); await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
