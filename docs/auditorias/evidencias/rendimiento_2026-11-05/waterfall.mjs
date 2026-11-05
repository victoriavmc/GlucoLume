// Waterfall de /ayuda en el perfil móvil simulado (CPU x4, Fast 3G de Chrome). Bytes transferidos reales (sizes()).
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
const p = await ctx.newPage();
const cdp = await ctx.newCDPSession(p);
await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
await cdp.send('Network.enable');
await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 562.5, downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 });
await p.route('**/api/**', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"no autenticado"}' }));
const t0 = Date.now(); const rows = [];
p.on('requestfinished', async (req) => {
  const s = await req.sizes().catch(() => null);
  rows.push({ t: Date.now() - t0, url: req.url().replace('http://localhost:4173', ''), transfer: s ? s.responseBodySize : null });
});
await p.addInitScript(() => { window.__lcp = 0; new PerformanceObserver((l) => { const e = l.getEntries(); window.__lcp = e[e.length - 1].startTime; }).observe({ type: 'largest-contentful-paint', buffered: true }); });
await p.goto('http://localhost:4173/ayuda', { waitUntil: 'load' });
await p.waitForSelector('figure.help-captura'); await p.waitForTimeout(3000);
const lcp = await p.evaluate(() => window.__lcp);
const fcp = await p.evaluate(() => performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null);
rows.sort((a, b) => a.t - b.t);
const pre = rows.filter((r) => r.t <= (fcp ?? 0));
console.log(JSON.stringify({ fcpMs: fcp, lcpMs: lcp, requests: rows.length, totalTransferKB: Math.round(rows.reduce((a, r) => a + (r.transfer || 0), 0) / 1024),
  beforeFcpRequests: pre.length, beforeFcpKB: Math.round(pre.reduce((a, r) => a + (r.transfer || 0), 0) / 1024) }));
for (const r of rows.filter((r) => !r.url.endsWith('.png'))) console.log(`${String(r.t).padStart(6)} ms  ${String(Math.round((r.transfer || 0) / 1024)).padStart(6)} KB  ${r.url}`);
console.log('png:', rows.filter((r) => r.url.endsWith('.png')).length, 'KB', Math.round(rows.filter((r) => r.url.endsWith('.png')).reduce((a, r) => a + (r.transfer || 0), 0) / 1024));
await b.close();
