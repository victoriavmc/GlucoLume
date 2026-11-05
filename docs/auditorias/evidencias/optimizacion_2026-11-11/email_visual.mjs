// Renderiza el correo de verificación con el banner viejo (PNG) y el nuevo (JPEG) y guarda capturas para comparar.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import fs from 'node:fs';
const SCR = process.env.SCR;
const b64 = (f) => fs.readFileSync(f).toString('base64');
const pngSrc = `data:image/png;base64,${b64(process.env.PNG_FILE)}`;
const jpgSrc = `data:image/jpeg;base64,${b64(process.env.JPG_FILE)}`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 700, height: 900 }, deviceScaleFactor: 1 });
for (const [name, html, src] of [['antes', 'before_verificacion.html', pngSrc], ['despues', 'after_verificacion.html', jpgSrc]]) {
  const doc = fs.readFileSync(`${SCR}/lab/${html}`, 'utf8').replaceAll('cid:bannerCorreoGlucoLume', src);
  await page.setContent(doc, { waitUntil: 'load' });
  await page.screenshot({ path: `${SCR}/lab/correo_${name}.png`, fullPage: true });
  const size = await page.evaluate(() => { const img = document.querySelector('img'); return { natural: [img.naturalWidth, img.naturalHeight], shown: [img.width, img.height] }; });
  console.log(name, JSON.stringify(size));
}
await browser.close();
