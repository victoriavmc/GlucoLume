// Sin interceptación: acceso directo, recarga, navegación interna desde la portada y captura visible.
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://127.0.0.1:8080';
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } });
  const p = await ctx.newPage(); const errores = [];
  p.on('pageerror', (e) => errores.push(String(e)));
  p.on('response', (r) => { if (r.status() >= 400) errores.push(r.status() + ' ' + r.url()); });
  const comprobar = async (etiqueta) => {
    await p.waitForSelector('section.help-topic', { timeout: 20000 });
    const temas = await p.locator('section.help-topic').count();
    const imgs = await p.locator('figure.help-captura img').count();
    const cargadas = await p.evaluate(() => [...document.querySelectorAll('figure.help-captura img')].filter((i) => i.complete && i.naturalWidth > 0).length);
    console.log(etiqueta.padEnd(34), 'temas=' + temas, 'figuras=' + imgs, 'miniaturas-ya-cargadas=' + cargadas, 'url=' + new URL(p.url()).pathname);
  };
  await p.goto(BASE + '/ayuda', { waitUntil: 'load' }); await comprobar('acceso directo /ayuda');
  await p.reload({ waitUntil: 'load' }); await comprobar('recarga (F5)');
  await p.goto(BASE + '/ayuda/', { waitUntil: 'load' }); await comprobar('acceso directo /ayuda/');
  await p.goto(BASE + '/', { waitUntil: 'load' });
  await p.getByRole('link', { name: 'Ayuda', exact: true }).first().click().catch(async () => { await p.locator('a[href="/ayuda"]').first().click(); });
  await comprobar('navegación interna desde portada');
  console.log('errores HTTP/JS:', errores.length ? errores.join(' | ') : 'ninguno');
  await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
