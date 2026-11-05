const { chromium } = require('playwright');
const DIST = process.env.DIST_INDEX;
const route = (ctx) => ctx.route(/\/ayuda\/?(\?.*)?$/, (r) => (r.request().resourceType() === 'document' ? r.fulfill({ path: DIST, contentType: 'text/html' }) : r.continue()));
const name = (u) => u.replace(/^.*\/(assets|ayuda)\//, '$1/');
(async () => {
  const b = await chromium.launch();
  // 1) Cobertura precisa de JS (CDP Profiler) en escritorio.
  {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } }); await route(ctx);
    const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p);
    await cdp.send('Profiler.enable'); await cdp.send('Profiler.startPreciseCoverage', { callCount: true, detailed: true });
    await p.goto('http://127.0.0.1:8080/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
    const { result } = await cdp.send('Profiler.takePreciseCoverage');
    const scripts = result.filter((s) => /\/assets\//.test(s.url));
    for (const s of scripts) {
      const total = s.functions.length ? Math.max(...s.functions.flatMap((f) => f.ranges.map((r) => r.endOffset))) : 0;
      if (total < 3000) continue;
      const mark = new Uint8Array(total);
      for (const f of s.functions) for (const r of f.ranges) if (r.count > 0) mark.fill(1, r.startOffset, Math.min(r.endOffset, total));
      let used = 0; for (let i = 0; i < total; i++) used += mark[i];
      console.log('JS-PRECISO', name(s.url).padEnd(38), 'bytes=' + total, 'usado=' + (100 * used / total).toFixed(1) + '%');
    }
    await ctx.close();
  }
  // 2) Cascada de carga en móvil simulado (CPU 4x, 1,6 Mbps, RTT 150 ms).
  {
    const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); await route(ctx);
    const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p);
    await cdp.send('Network.enable'); await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
    const start = {}; const end = {}; const type = {}; let t0 = null;
    cdp.on('Network.requestWillBeSent', (e) => { if (t0 === null) t0 = e.timestamp; start[e.requestId] = [e.request.url, e.timestamp]; });
    cdp.on('Network.loadingFinished', (e) => { end[e.requestId] = e.timestamp; });
    cdp.on('Network.responseReceived', (e) => { type[e.requestId] = e.type; });
    await p.goto('http://127.0.0.1:8080/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
    const rows = Object.keys(start).map((id) => ({ url: name(new URL(start[id][0]).pathname), inicioMs: Math.round((start[id][1] - t0) * 1000), finMs: end[id] ? Math.round((end[id] - t0) * 1000) : null, tipo: type[id] }))
      .filter((r) => !/\.png$|\.webp$/.test(r.url) || r.url.includes('/ayuda/miniaturas/')).sort((a, b) => a.inicioMs - b.inicioMs);
    console.log('CASCADA-MOVIL (solo JS/CSS/documento, y primeras miniaturas):');
    for (const r of rows.slice(0, 14)) console.log('  ' + String(r.inicioMs).padStart(6) + ' → ' + String(r.finMs).padStart(6) + ' ms  ' + r.url);
    console.log('  miniaturas (webp) pedidas en carga:', Object.values(start).filter(([u]) => u.includes('/ayuda/miniaturas/')).length, ' originales PNG pedidos en carga (sin visor):', Object.values(start).filter(([u]) => /\/ayuda\/[^/]+\.png$/.test(u)).length);
    await ctx.close();
  }
  // 3) CLS con desplazamiento real de rueda (escritorio), sin ninguna entrada del usuario contada como excluida.
  {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } }); await route(ctx);
    const p = await ctx.newPage();
    await p.addInitScript(() => { window.__shifts = []; new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__shifts.push({ v: e.value, input: e.hadRecentInput, t: e.startTime, sources: (e.sources || []).map((s) => (s.node && (s.node.nodeName + '.' + (s.node.className || '')) || '?').toString().slice(0, 60)) }))).observe({ type: 'layout-shift', buffered: true }); });
    await p.goto('http://127.0.0.1:8080/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
    await p.waitForTimeout(500);
    const before = await p.evaluate(() => window.__shifts.length);
    for (let i = 0; i < 40; i++) { await p.mouse.move(683, 400); await p.mouse.wheel(0, 300); await p.waitForTimeout(120); }
    await p.waitForTimeout(1500);
    const shifts = await p.evaluate((from) => window.__shifts.slice(from), before);
    const total = shifts.filter((s) => !s.input).reduce((a, s) => a + s.v, 0);
    console.log('CLS-SCROLL-RUEDA: cambios de diseño tras el inicio =', shifts.length, ' CLS acumulado (sin entradas) =', total.toFixed(4));
    console.log('  ejemplos:', JSON.stringify(shifts.slice(0, 3)));
    await ctx.close();
  }
  await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
