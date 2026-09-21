/* ¿Por qué la página de género no enseña canciones? Se mira la red y el DOM de verdad. */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = 'admin-pruebas@radiopv-test.com';
const CLAVE = 'clave-de-pruebas-larga-123';

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await c.newPage();
  p.on('response', async (r) => {
    const u = r.url();
    if (u.includes('/tracks') || u.includes('/playlists')) {
      let forma = '';
      try {
        const j = await r.json();
        forma = Array.isArray(j) ? `array(${j.length})` : `objeto(${Object.keys(j).slice(0, 6).join(',')})`;
      } catch { forma = '(sin json)'; }
      console.log(`   ${r.status()} ${u.replace(URL_BASE, '').slice(0, 80)} -> ${forma}`);
    }
  });
  p.on('pageerror', (e) => console.log('   JS ERROR: ' + String(e).split('\n')[0].slice(0, 140)));
  p.on('console', (m) => { if (m.type() === 'error') console.log('   CONSOLA: ' + m.text().slice(0, 140)); });

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(3500);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(1500);
  await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
  await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
  await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
  await p.waitForTimeout(4000);

  console.log('--- abriendo /genre/genre:pop ---');
  await p.goto(`${URL_BASE}/genre/genre:pop`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(7000);

  const datos = await p.evaluate(() => {
    const caja = document.querySelector('.genre-list');
    const filas = document.querySelectorAll('.song-details');
    const tarjetas = document.querySelectorAll('.grid-item-list__item, .card, [class*=grid]');
    return {
      textoCabecera: (document.querySelector('.genre-page-header h1') || {}).innerText || '',
      cajaAlto: caja ? caja.getBoundingClientRect().height : null,
      cajaScroll: caja ? caja.scrollHeight : null,
      cajaTexto: caja ? caja.innerText.slice(0, 300) : '(no hay .genre-list)',
      filasCancion: filas.length,
      tarjetas: tarjetas.length,
      titulos: [...document.querySelectorAll('h2, .grid-item-list h2, .list-title')].map((h) => h.innerText).slice(0, 6),
    };
  });
  console.log(JSON.stringify(datos, null, 1));
  await p.screenshot({ path: 'capturas/debug-genero.png' });
  await b.close();
})();
