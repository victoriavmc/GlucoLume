const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } });
  await ctx.route(/\/ayuda\/?(\?.*)?$/, (r) => (r.request().resourceType() === 'document' ? r.fulfill({ path: process.env.DIST_INDEX, contentType: 'text/html' }) : r.continue()));
  const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p); await cdp.send('Performance.enable');
  await p.goto('http://127.0.0.1:8080/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
  const sample = async () => { await cdp.send('HeapProfiler.collectGarbage'); const { metrics } = await cdp.send('Performance.getMetrics'); const m = Object.fromEntries(metrics.map((x) => [x.name, x.value])); return { heapMB: +(m.JSHeapUsedSize / 1048576).toFixed(2), nodos: m.Nodes, listeners: m.JSEventListeners }; };
  const out = [['inicio', await sample()]];
  for (const n of [10, 20, 40]) {
    for (let i = out.length * 0; i < n - (out.at(-1)[0] === 'inicio' ? 0 : 0); i++) break;
  }
  let opened = 0;
  for (const target of [10, 20, 40]) {
    while (opened < target) {
      await p.locator('figure.help-captura button.help-captura-boton').nth(opened % 5).click();
      await p.waitForSelector('.help-visor-img'); await p.keyboard.press('Escape');
      await p.waitForSelector('.help-visor-img', { state: 'detached' }).catch(() => {});
      opened++;
    }
    out.push([`tras ${target} visores`, await sample()]);
  }
  for (const [k, v] of out) console.log(k.padEnd(20), JSON.stringify(v));
  await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
