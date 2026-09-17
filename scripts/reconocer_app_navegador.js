/**
 * Reconocimiento de la app desplegada: abre la web, captura errores y lista los botones.
 *
 * Antes de probar el login hay que saber QUE botones existen de verdad y con que texto,
 * porque la app esta traducida y no tiene por que coincidir con lo que uno espera.
 *
 *   node reconocer.js http://192.168.1.139:8090
 */
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://192.168.1.139:8090';

(async () => {
  const navegador = await chromium.launch();
  const contexto = await navegador.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await contexto.newPage();

  const fallosRed = [];
  const erroresJs = [];
  const api = [];
  const consola = [];

  page.on('requestfailed', (r) =>
    fallosRed.push(`${r.method()} ${r.url()}  ->  ${r.failure()?.errorText}`));
  page.on('pageerror', (e) => erroresJs.push(String(e)));
  page.on('response', (r) => {
    if (r.url().includes('/api/')) api.push(`${r.status()}  ${r.url()}`);
  });
  page.on('console', (m) => {
    if (m.type() === 'error') consola.push(m.text().slice(0, 200));
  });

  console.log(`\n=== abriendo ${BASE} ===`);
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(6000);

  const titulo = await page.title();
  const texto = await page.evaluate(() => document.body.innerText.slice(0, 400));
  console.log(`  titulo : ${titulo}`);
  console.log(`  texto  : ${JSON.stringify(texto.slice(0, 200))}`);

  console.log('\n=== botones visibles ===');
  const botones = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('button, a[role="button"], .WhiteButton, [class*="Button"]')
      .forEach((el) => {
        const r = el.getBoundingClientRect();
        const visible = r.width > 0 && r.height > 0;
        const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
        if (visible && t) out.push({ texto: t.slice(0, 60), clase: el.className.toString().slice(0, 60) });
      });
    return out;
  });
  botones.forEach((b, i) => console.log(`  ${i + 1}. "${b.texto}"   [${b.clase}]`));
  if (!botones.length) console.log('  (ninguno)');

  console.log('\n=== peticiones a /api/ ===');
  const unicas = [...new Set(api)];
  unicas.slice(0, 15).forEach((p) => console.log(`  ${p}`));
  if (!unicas.length) console.log('  (ninguna: la app NO esta llamando a nuestra API)');

  console.log('\n=== peticiones fallidas ===');
  [...new Set(fallosRed)].slice(0, 15).forEach((f) => console.log(`  ${f}`));
  if (!fallosRed.length) console.log('  (ninguna)');

  console.log('\n=== errores de JavaScript ===');
  [...new Set(erroresJs)].slice(0, 10).forEach((e) => console.log(`  ${e.slice(0, 200)}`));
  if (!erroresJs.length) console.log('  (ninguno)');

  console.log('\n=== errores en consola ===');
  [...new Set(consola)].slice(0, 10).forEach((c) => console.log(`  ${c}`));
  if (!consola.length) console.log('  (ninguno)');

  await page.screenshot({ path: 'reconocimiento.png', fullPage: false });
  console.log('\n  captura: reconocimiento.png');

  await navegador.close();
})();
