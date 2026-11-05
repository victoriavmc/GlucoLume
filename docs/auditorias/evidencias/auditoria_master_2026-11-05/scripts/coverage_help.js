const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } });
  const p = await ctx.newPage();
  await ctx.route(/\/ayuda\/?(\?.*)?$/, (route) => (route.request().resourceType() === 'document' ? route.fulfill({ path: process.env.DIST_INDEX, contentType: 'text/html' }) : route.continue()));
  await p.coverage.startCSSCoverage(); await p.coverage.startJSCoverage();
  await p.goto('http://127.0.0.1:8080/ayuda', { waitUntil: 'load' });
  await p.waitForSelector('section.help-topic'); await p.waitForLoadState('networkidle');
  const css = await p.coverage.stopCSSCoverage(); const js = await p.coverage.stopJSCoverage();
  const name = (u) => u.replace(/^.*\/assets\//, 'assets/');
  const rep = {};
  for (const e of css) { const k = 'CSS ' + name(e.url); const total = e.text.length; let used = 0; for (const r of e.ranges) used += r.end - r.start; rep[k] = { total, used }; }
  for (const e of js) { const k = 'JS  ' + name(e.url); const total = e.source.length; const mark = new Uint8Array(total); for (const f of e.functions) for (const r of f.ranges) if (r.count > 0) mark.fill(1, r.startOffset, Math.min(r.endOffset, total)); let used = 0; for (let i = 0; i < total; i++) used += mark[i]; rep[k] = { total, used }; }
  for (const [k, v] of Object.entries(rep).sort()) if (v.total > 3000) console.log(k.padEnd(48), 'bytes=' + String(v.total).padStart(7), 'usado=' + (100 * v.used / v.total).toFixed(1) + '%');
  await b.close();
})();
