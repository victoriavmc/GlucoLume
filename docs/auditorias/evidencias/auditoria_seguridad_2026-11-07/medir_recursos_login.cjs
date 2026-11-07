// Cuenta los recursos y bytes de una carga en frío de /login con el Nginx local (B-5: estimar el beneficio de HTTP/2).
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--no-sandbox'] });
  const ctx = await b.newContext();
  const p = await ctx.newPage();
  let n = 0, bytes = 0; const porTipo = {};
  p.on('response', async (r) => {
    n++;
    const tipo = r.request().resourceType();
    porTipo[tipo] = (porTipo[tipo] || 0) + 1;
    try { const cuerpo = await r.body(); bytes += cuerpo.length; } catch (_) {}
  });
  await p.goto(process.argv[2] || 'http://127.0.0.1:8080/login', { waitUntil: 'networkidle' });
  console.log(JSON.stringify({ ruta: '/login', recursos: n, bytesAprox: bytes, porTipo }));
  await b.close();
})();
