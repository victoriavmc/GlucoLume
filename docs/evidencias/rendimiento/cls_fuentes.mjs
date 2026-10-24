// Diagnóstico de CLS: imprime cada desplazamiento de diseño (valor y elementos) de una pantalla, con la red lenta del informe.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const { chromium } = createRequire(import.meta.url)('playwright');
const IDS = JSON.parse(readFileSync(new URL('./resultados/seed_ids.json', import.meta.url), 'utf8'));
const [, , ruta, usuario, red = '3g'] = process.argv;
const BASE = 'http://localhost:18080';
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
await context.addInitScript(`window.__shifts=[];new PerformanceObserver((l)=>{for(const e of l.getEntries()){if(e.hadRecentInput)continue;window.__shifts.push({v:e.value,t:Math.round(e.startTime),s:(e.sources||[]).map(s=>(s.node?.nodeName||'?')+'.'+(s.node?.className||'').toString().slice(0,40)+' '+JSON.stringify(s.previousRect)+'->'+JSON.stringify(s.currentRect))});}}).observe({type:'layout-shift',buffered:true});`);
const login = await context.newPage();
await login.goto(`${BASE}/login`);
await login.getByLabel('Correo electrónico o usuario').fill(usuario);
await login.getByLabel('Contraseña', { exact: true }).fill(IDS.password);
await login.getByLabel('Recordarme').check();
await login.getByRole('button', { name: /^(Ingresar|Iniciar sesión)/ }).click();
await login.waitForURL(/\/app/); await login.waitForLoadState('networkidle'); await login.close();
const page = await context.newPage();
const cdp = await context.newCDPSession(page);
await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
if (red === '3g') { await cdp.send('Network.emulateNetworkConditions', { offline: false, downloadThroughput: 200000, uploadThroughput: 96000, latency: 150 }); await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 }); }
await page.goto(`${BASE}${ruta.replace('{inst}', IDS.idInstitucion)}`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
console.log(JSON.stringify(await page.evaluate(() => window.__shifts), null, 1));
await browser.close();
