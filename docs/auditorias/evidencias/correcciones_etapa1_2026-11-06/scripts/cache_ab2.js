// A/B sin interceptación: en cada instancia se cargan las 22 capturas que la guía pide al inicio (escritorio) con <img>,
// en dos visitas del mismo contexto (recarga). Se registra cada respuesta real (estado, Cache-Control, caché) con CDP.
const { chromium } = require('playwright');
const fs = require('fs');
const LISTA = JSON.parse(fs.readFileSync(process.env.LISTA, 'utf8'));
const bases = { antes_master: 'http://127.0.0.1:8082', despues_correccion: 'http://127.0.0.1:8080' };
(async () => {
  const b = await chromium.launch(); const out = {};
  for (const [nombre, base] of Object.entries(bases)) {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 800 } });
    const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p); await cdp.send('Network.enable');
    const reqs = {}; const eventos = [];
    cdp.on('Network.responseReceived', (e) => { if (e.response.url.includes('/ayuda/')) reqs[e.requestId] = { url: new URL(e.response.url).pathname, status: e.response.status, cc: e.response.headers['Cache-Control'] || e.response.headers['cache-control'] || null, fromDisk: !!e.response.fromDiskCache, fromMem: !!e.response.fromPrefetchCache }; });
    const enCache = new Set(); cdp.on('Network.requestServedFromCache', (e) => { enCache.add(e.requestId); });
    const visitas = {};
    for (const fase of ['primera', 'segunda']) {
      for (const k of Object.keys(reqs)) delete reqs[k]; enCache.clear();
      await p.goto(base + '/consejos', { waitUntil: 'load' });
      await p.evaluate((urls) => Promise.all(urls.map((u) => new Promise((res) => { const im = new Image(); im.onload = im.onerror = res; im.src = u; }))), LISTA.map((u) => base + u));
      await p.waitForTimeout(200);
      const r = Object.entries(reqs).map(([id, x]) => ({ ...x, servidoDesdeCache: enCache.has(id) }));
      visitas[fase] = { peticiones: r.length,
        desdeCache: r.filter((x) => x.servidoDesdeCache || x.fromDisk || x.fromMem).length,
        red304: r.filter((x) => x.status === 304).length,
        red200: r.filter((x) => x.status === 200 && !(x.servidoDesdeCache || x.fromDisk || x.fromMem)).length,
        cacheControl: [...new Set(r.map((x) => x.cc))].join(' | ') };
    }
    out[nombre] = visitas; await ctx.close();
  }
  console.log(JSON.stringify(out, null, 2)); fs.writeFileSync(process.env.OUT, JSON.stringify(out, null, 2));
  await b.close();
})().catch((e) => { console.error('FALLO', e.message); process.exit(1); });
