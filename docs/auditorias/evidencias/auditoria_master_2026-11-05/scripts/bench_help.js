// Medición de la pantalla de Ayuda (/ayuda) sobre el build de producción servido por Nginx (plantilla real del repo).
// Entorno: contenedor de laboratorio (4 vCPU), Chromium headless de Playwright. Sin backend (la guía es estática).
// Uso: node bench_help.js <url> <salida.json>
const { chromium } = require('playwright');
const fs = require('fs');

const TARGET = process.argv[2] || 'http://127.0.0.1:8080/ayuda';
const OUT = process.argv[3];
const REPS = Number(process.env.REPS || 5);

const pct = (arr, p) => { const a = [...arr].sort((x, y) => x - y); return a.length ? +a[Math.min(a.length - 1, Math.round(p * (a.length - 1)))].toFixed(1) : null; };
const summary = (arr) => ({ n: arr.length, p50: pct(arr, 0.5), p95: pct(arr, 0.95), max: pct(arr, 1) });

async function metrics(cdp) {
  const { metrics } = await cdp.send('Performance.getMetrics');
  const m = Object.fromEntries(metrics.map((x) => [x.name, x.value]));
  return { scriptMs: m.ScriptDuration * 1000, layoutMs: m.LayoutDuration * 1000, styleMs: m.RecalcStyleDuration * 1000, taskMs: m.TaskDuration * 1000,
    nodes: m.Nodes, jsHeapMB: m.JSHeapUsedSize / 1048576, domListeners: m.JSEventListeners };
}
const diff = (a, b) => Object.fromEntries(Object.keys(a).map((k) => [k, +(b[k] - a[k]).toFixed(2)]));

async function newPage(browser, profile) {
  const context = await browser.newContext({ viewport: profile.viewport, deviceScaleFactor: 1, serviceWorkers: 'block' });
  // Laboratorio: Nginx responde 403 a /ayuda (directorio público homónimo), así que la navegación de documento se sirve con
  // el index.html del build; todos los demás pedidos (assets, capturas) siguen yendo al Nginx real.
  await context.route(/\/ayuda\/?(\?.*)?$/, (route) => (route.request().resourceType() === 'document'
    ? route.fulfill({ path: process.env.DIST_INDEX, contentType: 'text/html' }) : route.continue()));
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send('Performance.enable');
  if (profile.cpu > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: profile.cpu });
  if (profile.net) await cdp.send('Network.enable').then(() => cdp.send('Network.emulateNetworkConditions', profile.net));
  const requests = [];
  page.on('requestfinished', async (req) => {
    const resp = await req.response();
    const size = resp ? (await resp.body().catch(() => Buffer.alloc(0))).length : 0;
    const headers = resp ? await resp.allHeaders() : {};
    requests.push({ url: new URL(req.url()).pathname, type: req.resourceType(), bytes: size, cacheControl: headers['cache-control'] || null, encoding: headers['content-encoding'] || null });
  });
  return { context, page, cdp, requests };
}

async function loadPage(browser, profile) {
  const { context, page, cdp, requests } = await newPage(browser, profile);
  await page.addInitScript(() => {
    window.__lt = [];
    new PerformanceObserver((list) => list.getEntries().forEach((e) => window.__lt.push(e.duration))).observe({ type: 'longtask', buffered: true });
    window.__lcp = 0; window.__cls = 0;
    new PerformanceObserver((list) => list.getEntries().forEach((e) => { window.__lcp = e.startTime; })).observe({ type: 'largest-contentful-paint', buffered: true });
    new PerformanceObserver((list) => list.getEntries().forEach((e) => { if (!e.hadRecentInput) window.__cls += e.value; })).observe({ type: 'layout-shift', buffered: true });
    window.__fcp = 0;
    new PerformanceObserver((list) => list.getEntries().forEach((e) => { if (e.name === 'first-contentful-paint') window.__fcp = e.startTime; })).observe({ type: 'paint', buffered: true });
  });
  const t0 = Date.now();
  await page.goto(TARGET, { waitUntil: 'load' });
  await page.waitForSelector('[role=tab][aria-selected=true]', { timeout: 60000 }); await page.waitForSelector('section.help-topic', { timeout: 60000 });
  const tReady = Date.now() - t0;
  await page.waitForLoadState('networkidle');
  const tIdle = Date.now() - t0;
  const web = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0];
    return { ttfbMs: nav.responseStart, domContentLoadedMs: nav.domContentLoadedEventEnd, loadMs: nav.loadEventEnd,
      fcpMs: window.__fcp, lcpMs: window.__lcp, cls: window.__cls, longTasksMs: window.__lt.reduce((a, b) => a + b, 0), longTaskCount: window.__lt.length,
      figures: document.querySelectorAll('figure.help-captura').length, imgs: document.querySelectorAll('img').length,
      imgsLoadedNow: [...document.querySelectorAll('img')].filter((i) => i.complete && i.naturalWidth > 0).length,
      domNodes: document.getElementsByTagName('*').length, tables: document.querySelectorAll('table').length,
      temas: document.querySelectorAll('section.help-topic').length };
  });
  const jsBytes = requests.filter((r) => r.type === 'script').reduce((a, r) => a + r.bytes, 0);
  const cssBytes = requests.filter((r) => r.type === 'stylesheet').reduce((a, r) => a + r.bytes, 0);
  const imgBytes = requests.filter((r) => r.type === 'image').reduce((a, r) => a + r.bytes, 0);
  const imgReqs = requests.filter((r) => r.type === 'image').length;
  const cpu = await metrics(cdp);
  return { page, context, cdp, requests, web: { ...web, tReadyMs: tReady, tIdleMs: tIdle }, transfer: { jsBytes, cssBytes, imgBytes, imgRequests: imgReqs, totalRequests: requests.length },
    cpuAfterLoad: cpu };
}

async function tabSwitch(page, cdp) {
  // Cambio de pestaña Cliente <-> Institucional: medimos el tiempo hasta dos cuadros pintados y el trabajo del motor.
  const label = await page.evaluate(() => document.querySelector('[role=tab][aria-selected=true]').textContent.trim());
  const target = label === 'Cliente' ? 'Institucional' : 'Cliente';
  const before = await metrics(cdp);
  const t0 = await page.evaluate(() => performance.now());
  await page.getByRole('tab', { name: target }).click();
  const paintMs = await page.evaluate((t) => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(() => res(performance.now() - t)))), t0);
  const after = await metrics(cdp);
  await page.waitForTimeout(150);
  return { to: target, paintMs, ...diff(before, after) };
}

async function scrollTest(page, cdp) {
  // Desplazamiento de toda la página en pasos de 300 px: cuadros con más de 50 ms (jank) y duración por cuadro.
  const total = await page.evaluate(() => document.documentElement.scrollHeight);
  const frames = await page.evaluate(() => new Promise((resolve) => {
    const deltas = []; let last = performance.now(); let y = 0; const max = document.documentElement.scrollHeight - innerHeight;
    function step(now) {
      deltas.push(now - last); last = now; y = Math.min(max, y + 300); window.scrollTo(0, y);
      if (y < max) requestAnimationFrame(step); else resolve(deltas.slice(1));
    }
    requestAnimationFrame(step);
  }));
  return { scrollHeightPx: total, frames: frames.length, frameP50Ms: pct(frames, 0.5), frameP95Ms: pct(frames, 0.95), jankFrames50ms: frames.filter((d) => d > 50).length, maxFrameMs: pct(frames, 1) };
}

async function visorTest(page) {
  // Abrir una captura ampliada y pasar entre capturas con la flecha derecha.
  const open = [];
  const navs = [];
  for (let i = 0; i < 3; i++) {
    const figures = page.locator('figure.help-captura button.help-captura-boton');
    const count = await figures.count();
    await figures.nth(Math.min(i * 7, count - 1)).scrollIntoViewIfNeeded();
    const t0 = await page.evaluate(() => performance.now());
    await figures.nth(Math.min(i * 7, count - 1)).click();
    await page.waitForSelector('.help-visor-img', { state: 'visible' });
    await page.waitForFunction(() => { const im = document.querySelector('.help-visor-img'); return im && im.complete && im.naturalWidth > 0; }, null, { timeout: 30000 });
    open.push(await page.evaluate((t) => performance.now() - t, t0));
    const bytesFull = await page.evaluate(() => { const im = document.querySelector('.help-visor-img'); return { w: im.naturalWidth, h: im.naturalHeight, src: im.src }; });
    open.push(null); open.pop();
    for (let k = 0; k < 5; k++) {
      const tn = await page.evaluate(() => performance.now());
      await page.keyboard.press('ArrowRight');
      await page.waitForFunction(() => { const im = document.querySelector('.help-visor-img'); return im && im.complete && im.naturalWidth > 0; }, null, { timeout: 30000 });
      navs.push(await page.evaluate((t) => performance.now() - t, tn));
    }
    await page.keyboard.press('Escape');
    await page.waitForSelector('.help-visor-img', { state: 'detached', timeout: 5000 }).catch(() => {});
    open.push({ dims: bytesFull });
  }
  return { abrirVisorMs: open.filter((x) => typeof x === 'number'), cambioCapturaMs: navs, ejemploOriginal: open.find((x) => x && x.dims)?.dims };
}

(async () => {
  const browser = await chromium.launch();
  const profiles = {
    escritorio: { viewport: { width: 1366, height: 800 }, cpu: 1 },
    movil_lento: { viewport: { width: 390, height: 844 }, cpu: 4, net: { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 } },
  };
  const result = { url: TARGET, reps: REPS, profiles: {} };
  for (const [name, profile] of Object.entries(profiles)) {
    const runs = [];
    for (let r = 0; r < REPS; r++) {
      const loaded = await loadPage(browser, profile);
      const { page, cdp, context } = loaded;
      const run = { carga: loaded.web, transferencia: loaded.transfer, cpuTrasCarga: loaded.cpuAfterLoad, cambiosPestana: [], scroll: null, visor: null };
      if (r === 0) {
        run.listaSolicitudesImagen = loaded.requests.filter((q) => q.type === 'image').slice(0, 5).map((q) => ({ url: q.url, bytes: q.bytes, cacheControl: q.cacheControl }));
        run.ejemplosCabeceras = loaded.requests.filter((q) => q.url.startsWith('/ayuda/') || q.url.startsWith('/assets/')).slice(0, 4).map((q) => ({ url: q.url, cacheControl: q.cacheControl, encoding: q.encoding }));
      }
      for (let k = 0; k < 4; k++) run.cambiosPestana.push(await tabSwitch(page, cdp));
      run.visor = await visorTest(page);
      run.scroll = await scrollTest(page, cdp);
      runs.push(run);
      await context.close();
    }
    const flat = (fn) => runs.map(fn);
    result.profiles[name] = {
      carga_resumen: {
        ttfbMs: summary(flat((x) => x.carga.ttfbMs)), domContentLoadedMs: summary(flat((x) => x.carga.domContentLoadedMs)),
        loadMs: summary(flat((x) => x.carga.loadMs)), fcpMs: summary(flat((x) => x.carga.fcpMs)), lcpMs: summary(flat((x) => x.carga.lcpMs)),
        cls: summary(flat((x) => x.carga.cls)), longTasksMs: summary(flat((x) => x.carga.longTasksMs)), tiempoReadyMs: summary(flat((x) => x.carga.tReadyMs)),
        tiempoNetworkIdleMs: summary(flat((x) => x.carga.tIdleMs)),
        nodosDOM: summary(flat((x) => x.carga.domNodes)), figuras: summary(flat((x) => x.carga.figures)), imagenesEnDOM: summary(flat((x) => x.carga.imgs)),
        imagenesCargadasAlInicio: summary(flat((x) => x.carga.imgsLoadedNow)), heapJsMB: summary(flat((x) => x.cpuTrasCarga.jsHeapMB)),
      },
      transferencia_resumen: { jsBytes: summary(flat((x) => x.transferencia.jsBytes)), cssBytes: summary(flat((x) => x.transferencia.cssBytes)),
        imgBytes: summary(flat((x) => x.transferencia.imgBytes)), imgRequests: summary(flat((x) => x.transferencia.imgRequests)),
        totalRequests: summary(flat((x) => x.transferencia.totalRequests)) },
      cambio_pestana: {
        paintMs: summary(runs.flatMap((x) => x.cambiosPestana.map((c) => c.paintMs))),
        scriptMs: summary(runs.flatMap((x) => x.cambiosPestana.map((c) => c.scriptMs))),
        styleMs: summary(runs.flatMap((x) => x.cambiosPestana.map((c) => c.styleMs))),
        layoutMs: summary(runs.flatMap((x) => x.cambiosPestana.map((c) => c.layoutMs))),
        taskMs: summary(runs.flatMap((x) => x.cambiosPestana.map((c) => c.taskMs))),
        nodosDeltaPorCambio: summary(runs.flatMap((x) => x.cambiosPestana.map((c) => c.nodes))),
      },
      scroll: { frameP50Ms: summary(flat((x) => x.scroll.frameP50Ms)), frameP95Ms: summary(flat((x) => x.scroll.frameP95Ms)),
        jankFrames50ms: summary(flat((x) => x.scroll.jankFrames50ms)), maxFrameMs: summary(flat((x) => x.scroll.maxFrameMs)), scrollHeightPx: summary(flat((x) => x.scroll.scrollHeightPx)) },
      visor: runs.some((x) => x.visor) ? { abrirMs: summary(runs.filter((x) => x.visor).flatMap((x) => x.visor.abrirVisorMs)),
        cambioCapturaMs: summary(runs.filter((x) => x.visor).flatMap((x) => x.visor.cambioCapturaMs)), ejemploOriginal: runs.find((x) => x.visor).visor.ejemploOriginal } : null,
      muestra_una_corrida: runs[0],
    };
  }
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(result, null, 2));
  console.log('OK', OUT);
})().catch((e) => { console.error('FALLO', e); process.exit(1); });
