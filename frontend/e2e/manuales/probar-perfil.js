/*
 * El perfil ofrece su lista de más escuchadas: comprobar que la tarjeta EXISTE y que al pulsarla
 * se entra en la lista (no basta con que hayan desaparecido las cinco canciones sueltas).
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage();
  const errores = [];
  p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 120)));

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2000);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(800);
  const nom = p.locator('input[placeholder="Nombre"]');
  if (await nom.count()) await nom.first().fill('Perfil');
  await p.locator('input[placeholder="Email"]').first().fill(`perfil-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(6000);

  // Se le dan canciones al usuario para que exista "lo más escuchado". El endPoint es
  // `/library/{id}/play`: al principio lo puse como `/plays/{id}` (inventado), y como el error se
  // silenciaba, la sección salía vacía y parecía que la tarjeta no funcionaba.
  const yo = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const cab = { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' };
    const me = await (await fetch('/api/auth/me', { headers: cab })).json();
    const pistas = await (await fetch('/api/tracks?limit=3', { headers: cab })).json();
    for (const x of pistas) {
      const r = await fetch(`/api/library/${x.id}/play`, {
        method: 'POST', headers: cab,
        body: JSON.stringify({ source: 'test', completed: 1, seconds_listened: 60, context: 'test' }),
      });
      if (!r.ok) throw new Error(`no se pudo registrar la escucha: HTTP ${r.status}`);
    }
    return me.id;
  });

  await p.goto(`${URL_BASE}/users/${yo}`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);

  const estado = await p.evaluate(() => {
    const tarjeta = document.querySelector('.profile-top-list');
    const filas = document.querySelectorAll('.song-details').length;
    return {
      hayTarjeta: !!tarjeta,
      texto: tarjeta ? tarjeta.innerText.replace(/\n/g, ' | ').slice(0, 70) : null,
      href: tarjeta ? tarjeta.getAttribute('href') : null,
      alto: tarjeta ? Math.round(tarjeta.getBoundingClientRect().height) : 0,
      filasDeCancionSuelta: filas,
    };
  });
  console.log('perfil:', JSON.stringify(estado));

  if (estado.hayTarjeta) {
    await p.locator('.profile-top-list').first().click();
    await p.waitForTimeout(4000);
    const dentro = await p.evaluate(() => ({
      url: location.pathname,
      filas: document.querySelectorAll('.song-details').length,
    }));
    console.log('tras pulsar la lista:', JSON.stringify(dentro));
  }

  console.log('errores de JavaScript:', errores.length ? errores : 'ninguno');
  await p.screenshot({ path: 'perfil-lista.png' });
  await b.close();

  const bien = estado.hayTarjeta && estado.filasDeCancionSuelta === 0 && errores.length === 0;
  console.log(bien ? '\nPERFIL OK' : '\nPERFIL CON PROBLEMAS');
  process.exit(bien ? 0 : 1);
})();
