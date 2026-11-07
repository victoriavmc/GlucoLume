// Aislamiento entre orígenes en Chromium (B-5). Requiere dos orígenes servidos por el mismo Nginx (localhost:8080 y 127.0.0.1:8080). Salida: resultados_aislamiento_navegador.txt.
// Aislamiento entre orígenes en Chromium (B-5). Dos orígenes reales servidos por el mismo Nginx: localhost:8080 (login) y 127.0.0.1:8080 (app).
// Solo lectura: no envía credenciales; el código de transferencia es ficticio y la API responde con error (esperado sin Google ni base).
const { chromium } = require('playwright');
const LOGIN = process.argv[2] || 'http://localhost:8080';
const APP = process.argv[3] || 'http://127.0.0.1:8080';
const out = [];
const check = (nombre, ok, detalle) => { out.push({ nombre, ok }); console.log(`${ok ? 'PASA' : 'FALLA'}  ${nombre}  ${detalle || ''}`); };

(async () => {
  const b = await chromium.launch({ args: ['--no-sandbox'] });
  const ctx = await b.newContext();
  const p = await ctx.newPage();
  const errores = [];
  const canjes = [];
  p.on('request', (r) => { if (r.url().includes('/api/v1/auth/google/exchange')) canjes.push(r.postData() || ''); });
  p.on('console', (m) => { if (m.type() === 'error' || /Cross-Origin|COOP|CORP/i.test(m.text())) errores.push(m.text().slice(0, 140)); });

  // 1) El login en su origen renderiza con las cabeceras nuevas.
  const r1 = await p.goto(`${LOGIN}/login`, { waitUntil: 'networkidle' });
  const montado1 = (await p.locator('#root').innerHTML()).length > 200;
  check('login en localhost renderiza', r1.status() === 200 && montado1, `HTTP ${r1.status()} COOP=${r1.headers()['cross-origin-opener-policy']} CORP=${r1.headers()['cross-origin-resource-policy']}`);

  // 2) Transferencia de sesión entre orígenes (originGuard.goToApp): navegación de nivel superior con código en el fragmento.
  await p.evaluate((app) => { window.location.replace(`${app}/auth/google/callback#code=CODIGO-DE-PRUEBA&recordar=1`); }, APP);
  await p.waitForURL(/127\.0\.0\.1:8080\/auth\/google\/callback/, { timeout: 20000 }).catch(() => {});
  await p.waitForLoadState('networkidle').catch(() => {});
  const url = p.url();
  const montado2 = (await p.locator('#root').innerHTML().catch(() => '')).length > 200;
  // La app lee el código del fragmento y limpia la URL (history.replaceState): se verifica que lo usó para canjear la sesión.
  check('transferencia entre orígenes llega al callback de la app', url === `${APP}/auth/google/callback` && canjes.some((c) => c.includes('CODIGO-DE-PRUEBA')), `url=${url} canjes=${canjes.length}`);
  check('la app renderiza tras la transferencia (no queda en blanco)', montado2, '');
  check('window.opener es null en la app (sin relación de ventana con el login)', await p.evaluate(() => window.opener === null), '');

  // 3) CORP: un <img> de otro origen hacia un estático nuestro se bloquea; el mismo recurso desde su propio origen carga.
  await p.goto(`${APP}/ayuda`, { waitUntil: 'networkidle' });
  const resultado = await p.evaluate((app) => new Promise((resolver) => {
    const cargar = (src) => new Promise((r) => { const i = new Image(); i.onload = () => r('ok'); i.onerror = () => r('error'); i.src = src; });
    Promise.all([cargar(`${app}/ayuda/cliente-menu-inicio.png?mismo=1`), cargar('http://localhost:8080/ayuda/cliente-menu-inicio.png?cruzado=1')])
      .then(([mismo, cruzado]) => resolver({ mismo, cruzado }));
  }), APP);
  check('CORP: imagen propia carga desde su origen', resultado.mismo === 'ok', `mismo=${resultado.mismo}`);
  check('CORP: el mismo estático pedido desde otro origen se bloquea (no-cors)', resultado.cruzado === 'error', `cruzado=${resultado.cruzado}`);

  // 4) La app sigue cargando y navegando dentro de su origen.
  await p.evaluate(() => document.querySelector('a[href="/consejos"]')?.click());
  await p.waitForURL(/\/consejos$/, { timeout: 15000 }).catch(() => {});
  check('navegación interna en la app con COOP/CORP', p.url().endsWith('/consejos'), p.url());
  await p.reload({ waitUntil: 'networkidle' });
  check('recarga en /consejos', (await p.locator('#root').innerHTML()).length > 200 && p.url().endsWith('/consejos'), '');

  // 5) Sin errores de COOP/CORP/COEP en consola durante todo el recorrido (los errores de red a la API son esperados sin base).
  const aislamiento = errores.filter((e) => /Cross-Origin|COOP|CORP/i.test(e));
  check('sin errores de consola por COOP/CORP/COEP', aislamiento.length === 0, aislamiento.slice(0, 2).join(' | ') || 'ninguno');

  await b.close();
  const fallos = out.filter((o) => !o.ok).length;
  console.log(`Resumen: ${out.length - fallos}/${out.length} pasan`);
  process.exit(fallos ? 1 : 0);
})().catch((e) => { console.error('ERROR', e.message); process.exit(2); });
