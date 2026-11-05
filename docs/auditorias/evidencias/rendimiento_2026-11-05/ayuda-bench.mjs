// Banco de medición de /ayuda (laboratorio local, build de producción servido en localhost). No toca el repositorio.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

const SCR = process.env.SCR;
const BASE = 'http://localhost:4173';
const RUNS = Number(process.env.RUNS || 10);
const OUT = path.join(SCR, 'lab', process.env.OUTFILE || 'ayuda-results.jsonl');
const ONLY = process.env.ONLY ? process.env.ONLY.split(',') : null;

const PROFILES = {
  escritorio: { viewport: { width: 1366, height: 768 }, dpr: 1, cpu: 1, net: null },
  // Móvil de gama media simulado: CPU 4× más lenta y red «Fast 3G» de Chrome DevTools (1,6 Mbps bajada, 750 kbps subida, RTT 562,5 ms).
  movilLento: { viewport: { width: 390, height: 844 }, dpr: 2, cpu: 4,
    net: { offline: false, latency: 562.5, downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 } },
};
const CONTROLS = {
  base: (route) => route.continue(),
  sinImagenes: (route) => route.abort(),
  webp840: (route) => {
    const name = path.basename(new URL(route.request().url()).pathname, '.png');
    const file = path.join(SCR, 'ayuda-webp840', `${name}.webp`);
    if (!fs.existsSync(file)) return route.abort();
    return route.fulfill({ status: 200, contentType: 'image/webp', body: fs.readFileSync(file) });
  },
};

const INIT = () => {
  window.__lt = [];
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]); }).observe({ type: 'longtask', buffered: true }); } catch (e) {}
  window.__lcp = 0;
  try { new PerformanceObserver((l) => { const es = l.getEntries(); window.__lcp = es[es.length - 1].startTime; }).observe({ type: 'largest-contentful-paint', buffered: true }); } catch (e) {}
  window.__frames = null; window.__rid = 0;
  window.__startFrames = () => { window.__frames = []; let last = null; const tick = (t) => { if (last !== null) window.__frames.push(t - last); last = t; window.__rid = requestAnimationFrame(tick); }; window.__rid = requestAnimationFrame(tick); };
  window.__stopFrames = () => { cancelAnimationFrame(window.__rid); const f = window.__frames.slice().sort((a, b) => a - b); window.__frames = null; return f; };
};

const pct = (arr, p) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };

async function runOne(browser, profileName, controlName, run) {
  const prof = PROFILES[profileName];
  const context = await browser.newContext({ viewport: prof.viewport, deviceScaleFactor: prof.dpr, serviceWorkers: 'block' });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  if (prof.cpu > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: prof.cpu });
  if (prof.net) await cdp.send('Network.enable').then(() => cdp.send('Network.emulateNetworkConditions', prof.net));
  await page.addInitScript(INIT);
  // La portada pública pide la sesión al arrancar: se responde 401 al instante para medir la página, no el backend (inexistente aquí).
  await page.route('**/api/**', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"no autenticado"}' }));
  await page.route('**/ayuda/*.png', CONTROLS[controlName]);

  const pngs = [];
  page.on('response', async (res) => {
    const url = res.url();
    if (/\/ayuda\/.*\.(png|webp)$/.test(url)) {
      const len = Number(res.headers()['content-length'] || 0);
      pngs.push({ t: Date.now(), bytes: len, url });
    }
  });

  const out = { profile: profileName, control: controlName, run };
  const tNav = Date.now();
  await page.goto(`${BASE}/ayuda`, { waitUntil: 'load', timeout: 180000 });
  await page.waitForSelector('figure.help-captura', { timeout: 180000 });
  out.openFigureMs = Date.now() - tNav;
  // Espera a que la red quede quieta (las imágenes que entran en el viewport terminan de bajar).
  await page.waitForLoadState('networkidle', { timeout: 180000 }).catch(() => {});
  await page.waitForTimeout(500);
  const open = await page.evaluate(() => ({
    fcpMs: (performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime ?? null,
    lcpMs: window.__lcp || null,
    longTaskMs: window.__lt.reduce((a, [, d]) => a + d, 0),
    longTasks: window.__lt.length,
    nodes: document.getElementsByTagName('*').length,
    figures: document.querySelectorAll('figure.help-captura').length,
    imgsComplete: [...document.images].filter((i) => i.complete).length,
  }));
  Object.assign(out, open);
  out.pngOpenCount = pngs.length;
  out.pngOpenBytes = pngs.reduce((a, p) => a + p.bytes, 0);

  // Cambio de pestaña: CLIENTE -> INSTITUCIONAL -> CLIENTE. Mide hasta dos cuadros tras el clic (confirmación + pintado).
  const switchTab = (key) => page.evaluate(async (key) => {
    const tab = document.getElementById(`ayuda-tipo-tab-${key}`);
    if (!tab) throw new Error(`no existe la pestaña ${key}`);
    const lt0 = window.__lt.length; const n0 = document.getElementsByTagName('*').length;
    const t0 = performance.now(); tab.click();
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
    const t1 = performance.now();
    const longs = window.__lt.slice(lt0).filter(([s]) => s >= t0 - 1);
    return { ms: t1 - t0, longTaskMs: longs.reduce((a, [, d]) => a + d, 0), nodesBefore: n0, nodesAfter: document.getElementsByTagName('*').length,
      figures: document.querySelectorAll('figure.help-captura').length };
  }, key);
  const before = pngs.length;
  out.tabToInstitucional = await switchTab('INSTITUCIONAL');
  await page.waitForTimeout(400);
  out.tabPngInstitucional = pngs.length - before;
  const mid = pngs.length;
  out.tabBackToCliente = await switchTab('CLIENTE');
  await page.waitForTimeout(400);
  out.tabPngCliente = pngs.length - mid;

  // Desplazamiento de lectura: 40 pasos de 350 px con 120 ms de pausa (ritmo de lectura), midiendo cuadros.
  await page.evaluate(() => { window.scrollTo(0, 0); window.__startFrames(); });
  const pngScrollStart = pngs.length;
  const scrollLt0 = await page.evaluate(() => window.__lt.length);
  for (let i = 0; i < 40; i++) {
    await page.evaluate(() => window.scrollBy(0, 350));
    await page.waitForTimeout(120);
  }
  const frames = await page.evaluate(() => window.__stopFrames());
  out.scrollPngCount = pngs.length - pngScrollStart;
  out.scrollFrames = frames.length;
  out.scrollFrameP50 = pct(frames, 0.5);
  out.scrollFrameP95 = pct(frames, 0.95);
  out.scrollFrameMax = frames.length ? frames[frames.length - 1] : null;
  out.scrollJank50 = frames.filter((f) => f > 50).length;
  out.scrollLongTaskMs = await page.evaluate((i) => window.__lt.slice(i).reduce((a, [, d]) => a + d, 0), scrollLt0);
  await page.waitForLoadState('networkidle', { timeout: 180000 }).catch(() => {});

  // Visor ampliado: abrir la primera captura visible y medir hasta que la imagen ampliada está decodificada.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(200);
  const tVis = Date.now();
  await page.evaluate(() => {
    const btn = document.querySelectorAll('.help-captura-boton')[0];
    btn.scrollIntoView({ block: 'center' });
    btn.click();
  });
  await page.waitForSelector('.help-visor-img', { timeout: 60000 });
  // Con el control «sinImagenes» la captura nunca llega: se mide solo que el visor abra y se informa si la imagen cargó.
  out.visorImgLoaded = await page.waitForFunction(() => { const i = document.querySelector('.help-visor-img'); return i && i.complete && i.naturalWidth > 0; }, null, { timeout: 15000 })
    .then(() => true).catch(() => false);
  out.visorMs = Date.now() - tVis;
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);

  // Memoria: heap JS y estimación de píxeles decodificados de todas las capturas cargadas (4 bytes por píxel).
  out.heapMB = await page.evaluate(() => (performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null));
  out.decodedImgMB = await page.evaluate(() => [...document.images].filter((i) => i.complete && i.naturalWidth > 0)
    .reduce((a, i) => a + i.naturalWidth * i.naturalHeight * 4, 0) / 1048576);
  out.totalPngBytesAfterRun = pngs.reduce((a, p) => a + p.bytes, 0);
  out.totalPngCountAfterRun = pngs.length;
  await context.close();
  return out;
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
const plan = [];
for (const profile of Object.keys(PROFILES)) for (const control of Object.keys(CONTROLS)) {
  if (ONLY && !ONLY.includes(`${profile}:${control}`)) continue;
  plan.push([profile, control]);
}
for (const [profile, control] of plan) {
  for (let run = 1; run <= RUNS; run++) {
    const started = Date.now();
    const browser = await chromium.launch();  // un navegador por corrida: evita que un cierre inesperado arrastre a las siguientes
    try {
      const res = await runOne(browser, profile, control, run);
      res.wallMs = Date.now() - started;
      fs.appendFileSync(OUT, JSON.stringify(res) + '\n');
      console.log(`${profile}/${control} run ${run}: open ${res.openFigureMs}ms fcp ${Math.round(res.fcpMs)} tab ${Math.round(res.tabToInstitucional.ms)}ms scrollP95 ${Math.round(res.scrollFrameP95)}ms visor ${res.visorMs}ms pngOpen ${res.pngOpenCount}`);
    } catch (e) {
      fs.appendFileSync(OUT, JSON.stringify({ profile, control, run, error: String(e).slice(0, 300) }) + '\n');
      console.log(`${profile}/${control} run ${run} ERROR ${String(e).slice(0, 200)}`);
    } finally { await browser.close().catch(() => {}); }
  }
}
console.log('DONE');
