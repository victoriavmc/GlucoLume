// Altura de la página de Ayuda al cargar (antes de que lleguen las miniaturas) frente a la altura con todas cargadas.
// Un salto de altura mientras el usuario baja es lo que percibe como "salto" de diseño, aunque no cuente como CLS.
const { chromium } = require('playwright');
const DIST = process.env.DIST_INDEX; const BASE = process.env.BASE;
(async () => {
  const b = await chromium.launch(); const res = [];
  for (let r = 0; r < 3; r++) {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } });
    await ctx.route(/\/ayuda\/?(\?.*)?$/, (q) => (q.request().resourceType() === 'document' ? q.fulfill({ path: DIST, contentType: 'text/html' }) : q.continue()));
    const p = await ctx.newPage();
    await p.goto(BASE + '/ayuda', { waitUntil: 'load' }); await p.waitForSelector('section.help-topic');
    const alAbrir = await p.evaluate(() => document.documentElement.scrollHeight);
    await p.waitForLoadState('networkidle');
    let alto = 0;
    for (let k = 0; k < 400; k++) { if (await p.evaluate(() => window.scrollY + innerHeight >= document.documentElement.scrollHeight - 4)) break; await p.evaluate(() => window.scrollBy(0, 500)); await p.waitForTimeout(90); }
    await p.waitForFunction(() => [...document.querySelectorAll('figure.help-captura img')].every((i) => i.complete && i.naturalWidth > 0), null, { timeout: 90000 });
    await p.waitForTimeout(500);
    const alFinal = await p.evaluate(() => document.documentElement.scrollHeight);
    res.push({ alAbrirPx: alAbrir, alFinalPx: alFinal, crecimientoPct: +(100 * (alFinal - alAbrir) / alFinal).toFixed(1) });
    await ctx.close();
  }
  console.log(JSON.stringify({ base: BASE, repeticiones: res }, null, 1));
  await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
