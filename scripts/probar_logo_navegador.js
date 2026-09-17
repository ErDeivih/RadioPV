/**
 * Verifica en un navegador REAL que la esquina superior izquierda ya no es de Spotify.
 *
 * Comprueba las dos cosas que pidio el usuario:
 *   1. el icono es el logo propio, no el de Spotify
 *   2. el enlace lleva a SU repositorio, no al del autor original
 *
 *   node probar-logo.js http://192.168.1.139:8090
 */
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://192.168.1.139:8090';
const ESPERADO = 'github.com/ErDeivih';
const PROHIBIDO = 'francoborrelli';

const resultados = [];
function check(nombre, ok, detalle = '') {
  resultados.push({ nombre, ok });
  console.log(`  [${ok ? 'OK ' : 'FALLO'}] ${nombre}${detalle ? '  ·  ' + detalle : ''}`);
}

(async () => {
  const navegador = await chromium.launch();
  const contexto = await navegador.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await contexto.newPage();

  // Se intercepta window.open para ver a donde iba sin salir de la pagina.
  await page.addInitScript(() => {
    window.__abiertas = [];
    window.open = (url, ...resto) => {
      window.__abiertas.push(String(url));
      return null;
    };
  });

  console.log(`\n=== ${BASE} ===`);
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(6000);

  // ---------------------------------------------------------------- 1. el icono
  console.log('\n=== 1. el icono de la esquina superior izquierda ===');
  const boton = page.locator('.navigation-button').first();
  check('existe el boton de arriba a la izquierda', await boton.count() > 0);

  const html = await boton.innerHTML().catch(() => '');
  const tieneImg = /<img/i.test(html);
  const tieneSvg = /<svg/i.test(html);
  check('el icono es una imagen (el logo propio)', tieneImg,
        tieneImg ? 'img encontrado' : `svg=${tieneSvg} html=${html.slice(0, 80)}`);

  if (tieneImg) {
    const src = await boton.locator('img').first().getAttribute('src');
    console.log(`        src: ${src}`);
    check('la imagen es un icono de la app', /icon-\d+\.png/.test(src || ''), src || '');
  }

  // El icono de Spotify era un SVG de react-icons: comprobar que ya no hay ninguno
  check('ya no hay ningun SVG de icono (el de Spotify era svg)', !tieneSvg,
        tieneSvg ? 'todavia hay un svg' : 'no hay svg');

  const etiqueta = await boton.getAttribute('aria-label').catch(() => null);
  console.log(`        titulo del boton: "${etiqueta}"`);

  // ---------------------------------------------------------------- 2. el enlace
  console.log('\n=== 2. a donde lleva el enlace ===');
  await boton.click({ timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1500);

  const abiertas = await page.evaluate(() => window.__abiertas || []);
  console.log(`        URL abierta: ${abiertas.join(', ') || '(ninguna)'}`);

  check('abre algo al pulsarlo', abiertas.length > 0);
  check('NO lleva al GitHub del autor original',
        !abiertas.some((u) => u.includes(PROHIBIDO)), abiertas.join(', '));
  check('lleva a TU repositorio', abiertas.some((u) => u.includes(ESPERADO)),
        abiertas.find((u) => u.includes(ESPERADO)) || 'no encontrado');

  // ---------------------------------------------------------------- 3. el resto de la app
  console.log('\n=== 3. el logo antiguo no aparece en ninguna parte de la pagina ===');
  const fuentes = await page.evaluate(() =>
    [...document.querySelectorAll('svg')].map((s) => s.getAttribute('data-icon') || '').join(' '));
  check('ningun icono de Spotify en el DOM', !/spotify/i.test(fuentes), fuentes.slice(0, 80) || '(sin iconos)');

  const todoElHtml = await page.content();
  check('el HTML no menciona al autor original', !todoElHtml.includes(PROHIBIDO));

  await page.screenshot({ path: 'logo-nuevo.png' });
  await navegador.close();

  const fallos = resultados.filter((r) => !r.ok);
  console.log(`\n  ===== ${resultados.length - fallos.length}/${resultados.length} comprobaciones OK =====`);
  if (fallos.length) {
    console.log('  fallos:');
    fallos.forEach((f) => console.log(`    - ${f.nombre}`));
    process.exit(1);
  }
})();
