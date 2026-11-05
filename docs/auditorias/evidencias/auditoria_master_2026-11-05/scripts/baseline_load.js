const { chromium } = require('playwright');
const fs = require('fs');
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return +s[Math.min(s.length - 1, Math.round(p * (s.length - 1)))].toFixed(1); };
(async () => {
  const b = await chromium.launch(); const out = {};
  const profiles = { escritorio: { viewport: { width: 1366, height: 800 }, cpu: 1, net: null },
    movil_lento: { viewport: { width: 390, height: 844 }, cpu: 4, net: { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 } } };
  for (const [pname, prof] of Object.entries(profiles)) for (const [label, path] of [['portada /', '/'], ['login /plataforma/login', '/plataforma/login'], ['ayuda /ayuda (ver nota)', '/ayuda']]) {
    const rs = [];
    for (let r = 0; r < 4; r++) {
      const ctx = await b.newContext({ viewport: prof.viewport, serviceWorkers: 'block' });
      if (path === '/ayuda') await ctx.route(/\/ayuda\/?(\?.*)?$/, (q) => (q.request().resourceType() === 'document' ? q.fulfill({ path: process.env.DIST_INDEX, contentType: 'text/html' }) : q.continue()));
      const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p); await cdp.send('Performance.enable');
      if (prof.cpu > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: prof.cpu });
      if (prof.net) { await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions', prof.net); }
      await p.addInitScript(() => { window.__lcp = 0; new PerformanceObserver((l) => l.getEntries().forEach((e) => { window.__lcp = e.startTime; })).observe({ type: 'largest-contentful-paint', buffered: true }); });
      let bytes = 0, reqs = 0; p.on('requestfinished', async (q) => { reqs++; const s = q.sizes ? q.sizes() : null; });
      cdp.on('Network.loadingFinished', (e) => { bytes += e.encodedDataLength; reqs += 0; });
      await p.goto('http://127.0.0.1:8080' + path, { waitUntil: 'load' }).catch(() => {});
      await p.waitForLoadState('networkidle').catch(() => {});
      const m = await p.evaluate(() => { const n = performance.getEntriesByType('navigation')[0]; return { load: n.loadEventEnd, dcl: n.domContentLoadedEventEnd, lcp: window.__lcp, nodos: document.getElementsByTagName('*').length, texto: document.body.innerText.slice(0, 60).replace(/\s+/g, ' ') }; });
      rs.push({ ...m, bytesRed: bytes });
      await ctx.close();
    }
    out[`${pname} | ${label}`] = { loadMs_p50: pct(rs.map((x) => x.load), 0.5), lcpMs_p50: pct(rs.map((x) => x.lcp), 0.5), dclMs_p50: pct(rs.map((x) => x.dcl), 0.5), nodos: rs[0].nodos, bytesRedKB_p50: pct(rs.map((x) => x.bytesRed / 1024), 0.5), muestraTexto: rs[0].texto };
  }
  console.log(JSON.stringify(out, null, 1)); fs.writeFileSync(process.env.OUT, JSON.stringify(out, null, 1));
  await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
