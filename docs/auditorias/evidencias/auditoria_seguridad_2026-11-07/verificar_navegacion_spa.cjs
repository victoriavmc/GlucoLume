# Navegación de la SPA en un Nginx real (B-2). Ver sondas_rutas_spa.sh para las rutas desconocidas. Requiere Playwright y el build del frontend.
// Navegación de la SPA contra el Nginx local (B-2). Solo lectura: no envía formularios ni credenciales.
// Uso: node navegacion.cjs BASE_URL
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:8080';
const resultados = [];
const registrar = (escenario, ok, detalle) => {
  resultados.push({ escenario, ok, detalle });
  console.log(`${ok ? 'PASA' : 'FALLA'}  ${escenario}  ${detalle || ''}`);
};

(async () => {
  const navegador = await chromium.launch({ args: ['--no-sandbox'] });
  const contexto = await navegador.newContext({ ignoreHTTPSErrors: true });
  const pagina = await contexto.newPage();
  const respuestas404 = [];
  pagina.on('response', (r) => { if (r.status() === 404) respuestas404.push(new URL(r.url()).pathname); });

  const renderizo = async () => (await pagina.locator('#root').innerHTML()).trim().length > 200;

  // 1) Navegación normal: clic dentro de la app (sin recargar la página).
  await pagina.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  // Clic por DOM sobre el <Link> de React Router (navegación del cliente, sin recargar). El enlace puede estar oculto según el viewport.
  await pagina.evaluate(() => document.querySelector('a[href="/consejos"]').click());
  await pagina.waitForURL(`${BASE}/consejos`);
  registrar('navegación: clic a /consejos desde la portada', await renderizo() && pagina.url() === `${BASE}/consejos`, pagina.url());

  // 2) Acceso directo a rutas públicas válidas (status 200 y la app renderiza).
  for (const ruta of ['/login', '/caracteristicas', '/ayuda', '/privacidad', '/consejos/abc', '/recuperar-contrasena', '/plataforma/login']) {
    const respuesta = await pagina.goto(`${BASE}${ruta}`, { waitUntil: 'networkidle' });
    const ok = respuesta.status() === 200 && await renderizo();
    registrar(`acceso directo ${ruta}`, ok, `HTTP ${respuesta.status()} url=${new URL(pagina.url()).pathname}`);
  }

  // 3) Recarga: la misma pantalla tras recargar (F5) sigue siendo la válida.
  await pagina.goto(`${BASE}/caracteristicas`, { waitUntil: 'networkidle' });
  await pagina.reload({ waitUntil: 'networkidle' });
  registrar('recarga en /caracteristicas', await renderizo() && pagina.url() === `${BASE}/caracteristicas`, pagina.url());

  // 4) Ruta privada sin sesión: la SPA la redirige a /login (control de acceso del frontend; la API sigue exigiendo autenticación).
  const priv = await pagina.goto(`${BASE}/app/inicio`, { waitUntil: 'networkidle' });
  registrar('acceso directo /app/inicio sin sesión redirige a login', priv.status() === 200 && pagina.url().includes('/login'), `HTTP ${priv.status()} -> ${new URL(pagina.url()).pathname}`);

  // 5) Rutas desconocidas y archivos sensibles: 404 real, sin shell.
  for (const ruta of ['/nonexistent-xyz', '/phpinfo.php', '/.git/config', '/.env', '/administracion/xyz']) {
    const respuesta = await pagina.goto(`${BASE}${ruta}`, { waitUntil: 'load' });
    const cuerpo = await pagina.content();
    const sinShell = !cuerpo.includes('id="root"');
    registrar(`desconocida ${ruta}`, respuesta.status() === 404 && sinShell, `HTTP ${respuesta.status()}`);
  }

  // 6) La API: rutas inexistentes responden JSON 404 de la API (no la shell), y las existentes siguen.
  const api = await pagina.evaluate(async () => {
    const pedir = async (ruta) => { const r = await fetch(ruta); return { status: r.status, tipo: r.headers.get('content-type') }; };
    return { inexistente: await pedir('/api/v1/no-existe'), salud: await pedir('/api/v1/healthz') };
  });
  registrar('API inexistente /api/v1/no-existe responde JSON 404', api.inexistente.status === 404 && api.inexistente.tipo.includes('application/json'), JSON.stringify(api.inexistente));
  registrar('API /api/v1/healthz sigue respondiendo 200 JSON', api.salud.status === 200 && api.salud.tipo.includes('application/json'), JSON.stringify(api.salud));

  // 7) Los recursos de la app no dan 404 al cargar una página válida (assets, ayuda, favicon).
  await pagina.goto(`${BASE}/ayuda`, { waitUntil: 'networkidle' });
  const sinRecursosRotos = respuestas404.filter((p) => p.startsWith('/assets/') || p.startsWith('/ayuda/') || p === '/favicon.svg');
  registrar('recursos de /ayuda y /assets sin 404', sinRecursosRotos.length === 0, sinRecursosRotos.join(', ') || 'ninguno');

  await navegador.close();
  const fallos = resultados.filter((r) => !r.ok).length;
  console.log(`\nResumen: ${resultados.length - fallos}/${resultados.length} pasan`);
  process.exit(fallos ? 1 : 0);
})().catch((e) => { console.error('ERROR', e); process.exit(2); });
