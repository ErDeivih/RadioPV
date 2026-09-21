/* Medir el LAYOUT de verdad: ¿dónde empieza y acaba el contenido en móvil y escritorio? */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';

const medir = async (p) => p.evaluate(() => {
  const caja = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), ancho: Math.round(r.width), alto: Math.round(r.height) };
  };
  // El contenedor del contenido: se busca el que envuelve la página
  const main = document.querySelector('main, .main, .content, #root > div > div');
  const anchoVentana = window.innerWidth;
  const desbordes = [...document.querySelectorAll('*')]
    .filter((el) => el.getBoundingClientRect().right > anchoVentana + 4)
    .slice(0, 5)
    .map((el) => `${el.tagName}.${String(el.className).split(' ').slice(0, 2).join('.')} (+${Math.round(el.getBoundingClientRect().right - anchoVentana)}px)`);
  return {
    ventana: `${anchoVentana}x${window.innerHeight}`,
    main: main ? caja('main') : null,
    barraIzquierda: caja('.sidebar, .nav-bar, aside, .library'),
    cabeceraGenero: caja('.genre-page-header h1'),
    contenedorGenero: caja('.genre-list'),
    primeraTarjeta: caja('.grid-item-list__item, .browse-card, .card'),
    desbordes,
  };
});

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  for (const [vista, tamano, movil] of [
    ['movil', { width: 390, height: 844 }, true],
    ['escritorio', { width: 1440, height: 900 }, false],
  ]) {
    const c = await b.newContext({ viewport: tamano, isMobile: movil, hasTouch: movil });
    const p = await c.newPage();
    for (const ruta of ['/', '/genre/genre:pop']) {
      await p.goto(URL_BASE + ruta, { waitUntil: 'domcontentloaded' });
      await p.waitForTimeout(5000);
      console.log(`\n=== ${vista} ${ruta} ===`);
      console.log(JSON.stringify(await medir(p), null, 1));
    }
    await c.close();
  }
  await b.close();
})();
