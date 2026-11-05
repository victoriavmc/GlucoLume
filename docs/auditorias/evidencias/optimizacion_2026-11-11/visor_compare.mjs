// Captura del visor abierto (primera captura visible tras desplazar) en master y en S-02 corregido, escritorio y móvil.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const SCR = process.env.SCR;
const b = await chromium.launch();
for (const [name, base] of [['master', 'http://localhost:4173'], ['s02', 'http://localhost:4177']]) {
  for (const [vp, w, h, dpr] of [['escritorio', 1366, 768, 1], ['movil', 390, 844, 2]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
    const p = await ctx.newPage();
    await p.route('**/api/**', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"no autenticado"}' }));
    await p.goto(`${base}/ayuda`, { waitUntil: 'load' });
    await p.waitForSelector('figure.help-captura');
    await p.evaluate(() => { const btn = document.querySelectorAll('.help-captura-boton')[0]; btn.scrollIntoView({ block: 'center' }); });
    await p.waitForTimeout(800);
    const t0 = Date.now();
    await p.evaluate(() => document.querySelectorAll('.help-captura-boton')[0].click());
    await p.waitForSelector('.help-visor-img', { state: 'visible', timeout: 20000 });
    const visible = Date.now() - t0;
    await p.waitForFunction(() => { const i = document.querySelector('.help-visor-img'); return i.complete && i.naturalWidth > 0; }, null, { timeout: 20000 });
    await p.waitForTimeout(300);
    const box = await p.evaluate(() => { const i = document.querySelector('.help-visor-img'); const r = i.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; });
    await p.screenshot({ path: `${SCR}/visor_${name}_${vp}.png` });
    console.log(name, vp, 'visibleMs', visible, 'imgBox', JSON.stringify(box));
    await ctx.close();
  }
}
await b.close();
