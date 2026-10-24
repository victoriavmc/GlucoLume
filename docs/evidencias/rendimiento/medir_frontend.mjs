// Mediciones del frontend con Playwright/Chromium contra el stack de medición (http://localhost:18080, base descartable GlucoLume_perf).
//   Requisitos: node >= 20 y `npm i playwright@1.49.1 && npx playwright install chromium` en una carpeta de trabajo (fuera del repositorio).
//   Uso:  NODE_PATH=<carpeta>/node_modules node medir_frontend.mjs --etiqueta base [--repeticiones 5] [--red rapida,3g] [--solo landing]
// Mide por pantalla y por condición de red: FCP, LCP, CLS, TBT (long tasks), carga (load), JS inicial transferido, solicitudes totales y a la API,
// y solicitudes repetidas. Las pantallas autenticadas se miden con el contexto ya iniciado (sesión por cookie, como un usuario recurrente) y la caché
// del navegador DESACTIVADA (carga fría) o ACTIVADA (recarga con recursos con hash ya en caché). INP: duración de eventos de interacción reales.
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const HERE = dirname(fileURLToPath(import.meta.url));
const IDS = JSON.parse(readFileSync(join(HERE, 'resultados', 'seed_ids.json'), 'utf8'));
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]?.startsWith('--') ? 'true' : all[i + 1] ?? 'true']] : acc), []));
const BASE = args.base ?? 'http://localhost:18080';
const REPS = Number(args.repeticiones ?? 5);
const LABEL = args.etiqueta ?? 'base';
const ONLY = args.solo ?? '';
const NETS = {
  rapida: null,
  // «Fast 3G» de Lighthouse/Chrome DevTools: 1,6 Mbps de bajada, 750 kbps de subida, 150 ms de latencia; CPU 4x más lenta (móvil medio).
  '3g': { download: (1.6 * 1024 * 1024) / 8, upload: (750 * 1024) / 8, latency: 150, cpu: 4 },
};
const networks = (args.red ?? 'rapida,3g').split(',');

const OBSERVERS = `
  window.__m = { lcp: 0, cls: 0, fcp: 0, longTasks: [], events: [], shifts: [] };
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__m.lcp = e.startTime; }).observe({ type: 'largest-contentful-paint', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__m.cls += e.value; window.__m.shifts.push([Math.round(e.startTime), Math.round(e.value * 1000) / 1000, (e.sources || []).map((x) => (x.node ? x.node.nodeName : '?') + '.' + String(x.node ? x.node.className : '').slice(0, 30) + ' y' + Math.round(x.previousRect.y) + '>' + Math.round(x.currentRect.y) + ' h' + Math.round(x.previousRect.height) + '>' + Math.round(x.currentRect.height))]); } }).observe({ type: 'layout-shift', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') window.__m.fcp = e.startTime; }).observe({ type: 'paint', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__m.longTasks.push([e.startTime, e.duration]); }).observe({ type: 'longtask', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.interactionId) window.__m.events.push([e.name, e.duration]); }).observe({ type: 'event', durationThreshold: 16, buffered: true });
`;

async function login(context, user) {
  const page = await context.newPage();
  await page.goto(`${BASE}/login`);
  await page.getByLabel('Correo electrónico o usuario').fill(user);
  await page.getByLabel('Contraseña', { exact: true }).fill(IDS.password);
  await page.getByLabel('Recordarme').check();
  await Promise.all([page.waitForResponse((r) => r.url().includes('/auth/login') && r.status() === 200), page.getByRole('button', { name: /^(Ingresar|Iniciar sesión)/ }).click()]);
  await page.waitForURL(/\/app|\/plataforma/, { timeout: 20000 });
  await page.waitForLoadState('networkidle');
  await page.close();
}

const inst = IDS.idInstitucion;
const SCREENS = [
  { id: 'landing', ruta: '/', usuario: null },
  { id: 'login', ruta: '/login', usuario: null },
  { id: 'privacidad', ruta: '/privacidad', usuario: null },
  { id: 'inicio-individual', ruta: '/app/inicio', usuario: 'perfconsumidor' },
  { id: 'historial', ruta: '/app/mediciones/historial', usuario: 'perfconsumidor' },
  { id: 'pacientes', ruta: `/app/instituciones/${inst}/pacientes`, usuario: IDS.operadores[0].usuario },
  { id: 'dashboard-institucion', ruta: `/app/instituciones/${inst}`, usuario: 'perfduenia' },
  { id: 'dashboard-operador', ruta: `/app/instituciones/${inst}/personal/operadores/${IDS.operadores[0].idInstitucionUsuario}`, usuario: 'perfduenia' },
];

const median = (v) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : null; };
const r1 = (n) => (n === null || n === undefined ? null : Math.round(n * 10) / 10);

async function measure(page, cdp, url, { cold }) {
  const requests = [];
  const sizes = new Map();
  cdp.on('Network.responseReceived', (e) => requests.push({ id: e.requestId, url: e.response.url, type: e.type, status: e.response.status }));
  cdp.on('Network.loadingFinished', (e) => sizes.set(e.requestId, e.encodedDataLength));
  const t0 = Date.now();
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  const loadMs = Date.now() - t0;
  await page.waitForLoadState('networkidle', { timeout: 60000 }).catch(() => {});
  const idleMs = Date.now() - t0;
  await page.waitForTimeout(800);
  const m = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0];
    const tbt = window.__m.longTasks.reduce((sum, [, d]) => sum + Math.max(0, d - 50), 0);
    return { ...window.__m, tbt, dcl: nav.domContentLoadedEventEnd, loadEvt: nav.loadEventEnd, ttfb: nav.responseStart };
  });
  cdp.removeAllListeners('Network.responseReceived');
  cdp.removeAllListeners('Network.loadingFinished');
  const js = requests.filter((r) => r.type === 'Script');
  const css = requests.filter((r) => r.type === 'Stylesheet');
  const api = requests.filter((r) => r.url.includes('/api/v1/'));
  const apiPaths = api.map((r) => r.url.replace(BASE, '').replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, '{id}'));
  const dup = apiPaths.filter((p, i) => apiPaths.indexOf(p) !== i);
  const bytes = (list) => list.reduce((s, r) => s + (sizes.get(r.id) ?? 0), 0);
  return {
    loadMs, idleMs, fcp: m.fcp, lcp: m.lcp, cls: m.cls, tbt: m.tbt, ttfb: m.ttfb, dcl: m.dcl,
    jsBytes: bytes(js), jsFiles: js.length, cssBytes: bytes(css), totalBytes: bytes(requests), requests: requests.length, apiRequests: api.length,
    apiPaths, repetidas: dup, noOk: api.filter((r) => r.status >= 400).map((r) => `${r.status} ${r.url.replace(BASE, '')}`),
  };
}

const browser = await chromium.launch();
const out = { etiqueta: LABEL, base: BASE, fecha: new Date().toISOString(), repeticiones: REPS, resultados: {} };

for (const netName of networks) {
  const net = NETS[netName];
  for (const screen of SCREENS) {
    if (ONLY && !screen.id.includes(ONLY)) continue;
    for (const cold of [true, false]) {
      if (!screen.usuario && !cold) continue; // público: solo carga fría
      const runs = [];
      // Un solo inicio de sesión por pantalla y condición (el login tiene límite por IP); las repeticiones reabren la página en el mismo contexto.
      const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      await context.addInitScript(OBSERVERS);
      if (screen.usuario) await login(context, screen.usuario);
      if (!cold) { // llena la caché con los recursos con hash antes de medir
        const warm = await context.newPage();
        await warm.goto(`${BASE}${screen.ruta}`, { waitUntil: 'networkidle' });
        await warm.close();
      }
      for (let i = 0; i < REPS; i += 1) {
        const page = await context.newPage();
        const cdp = await context.newCDPSession(page);
        await cdp.send('Network.enable');
        await cdp.send('Network.setCacheDisabled', { cacheDisabled: cold });
        if (net) {
          await cdp.send('Network.emulateNetworkConditions', { offline: false, downloadThroughput: net.download, uploadThroughput: net.upload, latency: net.latency });
          await cdp.send('Emulation.setCPUThrottlingRate', { rate: net.cpu });
        }
        try {
          runs.push(await measure(page, cdp, `${BASE}${screen.ruta}`, { cold }));
          if (process.env.DEBUG_RUNS) console.log(JSON.stringify(await page.evaluate(() => window.__m.shifts)));
          if (process.env.DEBUG_RUNS) console.log('   corrida', i + 1, 'CLS', runs.at(-1).cls, 'LCP', Math.round(runs.at(-1).lcp), 'FCP', Math.round(runs.at(-1).fcp));
        } catch (error) {
          runs.push({ error: String(error).slice(0, 200) });
        }
        await page.close();
      }
      await context.close();
      const ok = runs.filter((r) => !r.error);
      const key = `${screen.id} | ${netName} | ${cold ? 'fría' : 'caché'}`;
      const pick = (f) => r1(median(ok.map(f)));
      out.resultados[key] = ok.length ? {
        n: ok.length, fallos: runs.length - ok.length, loadMs: pick((r) => r.loadMs), idleMs: pick((r) => r.idleMs), fcp: pick((r) => r.fcp), lcp: pick((r) => r.lcp),
        cls: Math.round(median(ok.map((r) => r.cls)) * 1000) / 1000, tbt: pick((r) => r.tbt), jsKB: pick((r) => r.jsBytes / 1024), jsFiles: pick((r) => r.jsFiles),
        cssKB: pick((r) => r.cssBytes / 1024), totalKB: pick((r) => r.totalBytes / 1024), solicitudes: pick((r) => r.requests), api: pick((r) => r.apiRequests),
        apiPaths: ok[0].apiPaths, repetidas: ok[0].repetidas, noOk: ok[0].noOk,
      } : { error: runs[0].error };
      const r = out.resultados[key];
      console.log(`${key.padEnd(46)} ${r.error ? r.error : `load ${r.loadMs} ms · FCP ${r.fcp} · LCP ${r.lcp} · CLS ${r.cls} · TBT ${r.tbt} · JS ${r.jsKB} KB/${r.jsFiles} · total ${r.totalKB} KB · ${r.solicitudes} sol. (${r.api} API) · repetidas ${JSON.stringify(r.repetidas)}`}`);
    }
  }
}
await browser.close();
writeFileSync(join(HERE, 'resultados', `frontend_${LABEL}.json`), JSON.stringify(out, null, 2));
