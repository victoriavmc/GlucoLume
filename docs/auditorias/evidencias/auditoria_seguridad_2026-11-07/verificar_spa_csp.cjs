// Verificación de navegador del SPA servido por Nginx (B-3, auditoría 07/11/2026). Solo lectura. No usar contra producción.
//
// Uso: node verificar_spa_csp.cjs [URL_BASE]     (por defecto http://127.0.0.1:8080)
//
// Para cada página registra: código HTTP, si React monta (#root con contenido), excepciones de página, errores de consola y las
// violaciones de Content-Security-Policy. Las violaciones se cuentan aparte: son las que una cabecera mal puesta podría provocar.
// Los recursos de terceros (p. ej. cdn.jsdelivr.net para Swagger) se cuentan como fallos de red, no de CSP, y se indican.
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:8080';
const PAGINAS = [
  '/', '/login', '/registro', '/ayuda', '/caracteristicas', '/privacidad', '/plataforma/login',
  '/ruta-que-no-existe', '/docs', '/api/v1/healthz', '/api/v1/auth/google/login',
];

(async () => {
  const navegador = await chromium.launch();
  for (const ruta of PAGINAS) {
    const contexto = await navegador.newContext();
    const pagina = await contexto.newPage();
    const errores = [];
    const csp = [];
    const red = [];
    pagina.on('pageerror', (e) => errores.push(`excepción: ${e.message.slice(0, 120)}`));
    pagina.on('console', (m) => {
      const texto = m.text();
      if (/Content Security Policy|Refused to/i.test(texto)) csp.push(texto.slice(0, 160));
      else if (m.type() === 'error') errores.push(texto.slice(0, 160));
    });
    pagina.on('requestfailed', (r) => red.push(`${r.url().split('/').slice(0, 3).join('/')} ${r.failure()?.errorText || ''}`));
    let codigo = null;
    try {
      const respuesta = await pagina.goto(BASE + ruta, { waitUntil: 'load', timeout: 20000 });
      codigo = respuesta ? respuesta.status() : null;
      await pagina.waitForTimeout(1500);
    } catch (error) {
      errores.push(`navegación: ${String(error.message).slice(0, 120)}`);
    }
    const montado = await pagina.evaluate(() => {
      const raiz = document.getElementById('root');
      return raiz ? raiz.childElementCount > 0 : null;
    }).catch(() => null);
    console.log(JSON.stringify({ ruta, codigo, reactMontado: montado, violacionesCSP: csp.length, ejemplosCSP: csp.slice(0, 2),
      erroresConsola: errores.length, ejemplosError: errores.slice(0, 2), fallosRed: red.length, ejemplosRed: red.slice(0, 2) }));
    await contexto.close();
  }
  await navegador.close();
})();
