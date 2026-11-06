// Para cada instancia (variable BASE y ETIQUETA): (1) captura de página completa en escritorio tras cargar todas las miniaturas;
// (2) CLS con desplazamiento de rueda real en móvil lento (CPU 4x, 1,6 Mbps, RTT 150 ms), sin entradas excluidas.
const { chromium } = require('playwright');
const fs = require('fs');
const DIST = process.env.DIST_INDEX; const BASE = process.env.BASE; const ETIQUETA = process.env.ETIQUETA; const OUT = process.env.OUT;
(async () => {
  const b = await chromium.launch(); const res = { etiqueta: ETIQUETA, base: BASE };
  const intercept = (ctx) => ctx.route(/\/ayuda\/?(\?.*)?$/, (r) => (r.request().resourceType() === 'document' ? r.fulfill({ path: DIST, contentType: 'text/html' }) : r.continue()));
  // (1) captura de escritorio
  {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } }); await intercept(ctx);
    const p = await ctx.newPage();
    await p.goto(BASE + '/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
    let alto = 0;
    for (let k = 0; k < 400; k++) { // recalcula el fondo: la página crece al cargar cada miniatura
      const fin = await p.evaluate(() => window.scrollY + innerHeight >= document.documentElement.scrollHeight - 4);
      if (fin) break;
      await p.evaluate(() => window.scrollBy(0, 500)); await p.waitForTimeout(90);
    }
    alto = await p.evaluate(() => document.documentElement.scrollHeight);
    await p.waitForTimeout(1200);
    await p.waitForFunction(() => [...document.querySelectorAll('figure.help-captura img')].every((i) => i.complete && i.naturalWidth > 0), null, { timeout: 60000 });
    await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(400);
    await p.screenshot({ path: OUT.replace('.json', `_${ETIQUETA}_escritorio.png`), fullPage: true });
    res.escritorioAltoPagina = alto; await ctx.close();
  }
  // (2) CLS con rueda en móvil lento
  for (const rep of [1, 2, 3]) {
    const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); await intercept(ctx);
    const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p); await cdp.send('Performance.enable');
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
    await p.addInitScript(() => { window.__cls = []; new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__cls.push({ v: e.value, input: e.hadRecentInput }))).observe({ type: 'layout-shift', buffered: true }); });
    await p.goto(BASE + '/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
    await p.waitForTimeout(300);
    const t0 = Date.now();
    for (let i = 0; i < 60; i++) { await p.touchscreen.tap(195, 500).catch(() => {}); await p.mouse.wheel(0, 0); await p.evaluate(() => window.scrollBy(0, 200)); await p.waitForTimeout(120); }
    await p.waitForTimeout(1500);
    const shifts = await p.evaluate(() => window.__cls);
    const cls = shifts.filter((s) => !s.input).reduce((a, s) => a + s.v, 0);
    res['clsMovilScroll_rep' + rep] = { cls: +cls.toFixed(4), desplazamientos: shifts.filter((s) => !s.input).length, duracionMs: Date.now() - t0 };
    await ctx.close();
  }
  fs.writeFileSync(OUT.replace('.json', `_${ETIQUETA}.json`), JSON.stringify(res, null, 2));
  console.log(JSON.stringify(res, null, 2));
  await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
