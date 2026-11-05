const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } });
  await ctx.route(/\/ayuda\/?(\?.*)?$/, (r) => (r.request().resourceType() === 'document' ? r.fulfill({ path: process.env.DIST_INDEX, contentType: 'text/html' }) : r.continue()));
  const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p); await cdp.send('Performance.enable');
  await p.goto('http://127.0.0.1:8080/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
  const sample = async (label) => { await cdp.send('HeapProfiler.collectGarbage'); const { metrics } = await cdp.send('Performance.getMetrics'); const m = Object.fromEntries(metrics.map((x) => [x.name, x.value]));
    const dom = await p.evaluate(() => document.getElementsByTagName('*').length); console.log(label.padEnd(28), 'heapMB=' + (m.JSHeapUsedSize / 1048576).toFixed(2), 'nodos=' + m.Nodes, 'nodosDOM=' + dom, 'listeners=' + m.JSEventListeners); };
  await sample('inicio');
  for (let i = 0; i < 30; i++) { await p.getByRole('tab', { name: i % 2 ? 'Cliente' : 'Institucional' }).click(); await p.waitForTimeout(40); }
  await sample('tras 30 cambios de pestaña');
  for (let i = 0; i < 20; i++) { await p.locator('figure.help-captura button.help-captura-boton').nth(i % 5).click(); await p.waitForSelector('.help-visor-img'); await p.keyboard.press('ArrowRight'); await p.keyboard.press('Escape'); await p.waitForSelector('.help-visor-img', { state: 'detached' }).catch(() => {}); }
  await sample('tras 20 visores abiertos');
  for (let i = 0; i < 30; i++) { await p.getByRole('tab', { name: i % 2 ? 'Cliente' : 'Institucional' }).click(); await p.waitForTimeout(40); }
  await sample('tras 30 cambios más');
  await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
