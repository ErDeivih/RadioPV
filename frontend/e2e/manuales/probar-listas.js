/*
 * Ciclo de vida de una lista en el MÓVIL: crear, renombrar, borrar y reproducir.
 *
 * Es lo que el usuario dice que no le funciona. La lista se crea por la API (para no depender de
 * encontrar el botón de crear, que es otra cosa) y el resto se hace como lo haría una persona con
 * el dedo: abrir la lista, tocar los tres puntos, elegir "Editar detalles", cambiar el nombre,
 * guardar, tocar los tres puntos otra vez y borrar.
 *
 * Uso: node probar-listas.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';

const res = [];
const ok = (n, bien, detalle = '') => {
  res.push({ n, bien });
  console.log(`  ${bien ? 'OK   ' : 'FALLO'}  ${n}${detalle ? `  ->  ${detalle}` : ''}`);
};

(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage();
  const errores = [];
  p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 140)));

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2500);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Listas');
  await p.locator('input[placeholder="Email"]').first().fill(`ciclo-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(8000);
  ok('sesión iniciada', !/inicia sesión para acceder/i.test(await p.evaluate(() => document.body.innerText)));

  // 1) Crear la lista POR LA INTERFAZ si se encuentra el botón; si no, por la API.
  const creada = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const r = await fetch('/api/playlists', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Ciclo de prueba' }),
    });
    return r.ok ? (await r.json()).id : null;
  });
  ok('la lista se crea', creada !== null, `id=${creada}`);

  // 2) Abrirla y buscar el botón de los tres puntos
  await p.goto(`${URL_BASE}/playlist/${creada}`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);
  ok('la lista se abre con el nombre puesto', (await p.evaluate(() => document.body.innerText)).includes('Ciclo de prueba'));

  const puntos = p.locator('.playlist-controls .scale').first();
  comprobarPuntos();
  function comprobarPuntos() {}
  const hayPuntos = await puntos.count();
  ok('existe el botón de opciones (tres puntos)', hayPuntos > 0);
  ok('el botón de opciones se ve y se puede tocar',
    hayPuntos > 0 && (await puntos.first().isVisible()),
    hayPuntos ? JSON.stringify(await puntos.first().boundingBox()) : 'no está');

  if (hayPuntos) {
    await puntos.first().click({ timeout: 8000 }).catch((e) => console.log('    (el toque falló: ' + String(e).split('\n')[0].slice(0, 80) + ')'));
    await p.waitForTimeout(2000);
    const items = await p.evaluate(() =>
      [...document.querySelectorAll('.ant-dropdown li, .ant-dropdown-menu-item, [role="menuitem"]')]
        .map((x) => (x.textContent || '').trim()).filter(Boolean));
    ok('al tocarlo se abre el menú de la lista', items.length > 0, items.join(' · ') || 'no se abrió nada');

    // 3) Renombrar
    const editar = p.getByText(/editar|renombrar|edit details/i).first();
    if (await editar.count()) {
      await editar.click().catch(() => undefined);
      await p.waitForTimeout(2000);
      const campo = p.locator('input[type="text"], input[name="name"], input[id*="name"]').first();
      if (await campo.count()) {
        await campo.fill('Ciclo renombrado');
        await p.waitForTimeout(500);
        const guardar = p.getByRole('button', { name: /guardar|save/i }).first();
        if (await guardar.count()) {
          await guardar.click().catch(() => undefined);
          await p.waitForTimeout(3000);
          const nombre = await p.evaluate(() => document.body.innerText.split('\n').slice(0, 6).join(' | '));
          ok('el cambio de nombre se guarda', nombre.includes('Ciclo renombrado'), nombre.slice(0, 80));
        } else {
          ok('hay botón de guardar en el diálogo', false);
        }
      } else {
        ok('el diálogo de editar tiene campo de nombre', false);
      }
    } else {
      ok('el menú ofrece editar/renombrar', false);
    }
  }

  // 4) Reproducir la lista entera (con la cola llena, no una canción suelta)
  const play = p.locator('.playlist-controls button[aria-label="Reproducir"]').first();
  if (await play.count()) {
    await play.click().catch(() => undefined);
    await p.waitForTimeout(6000);
    const est = await p.evaluate(() => {
      const a = window.__audio;
      const ms = navigator.mediaSession && navigator.mediaSession.metadata;
      return { hay: !!a, t: a ? +a.currentTime.toFixed(1) : 0, pausado: a ? a.paused : null, titulo: ms ? ms.title : null };
    });
    ok('el botón de la lista empieza a sonar', est.hay && est.pausado === false && est.t > 0.5, `t=${est.t}s ${est.titulo ?? ''}`);
  } else {
    ok('la lista tiene botón de reproducir', false);
  }

  // 5) Borrar
  if (hayPuntos) {
    await p.goto(`${URL_BASE}/playlist/${creada}`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);
    await p.locator('.playlist-controls .scale').first().click().catch(() => undefined);
    await p.waitForTimeout(1500);
    const borrar = p.getByText(/eliminar|borrar|delete/i).first();
    if (await borrar.count()) {
      await borrar.click().catch(() => undefined);
      await p.waitForTimeout(1500);
      const confirmar = p.getByRole('button', { name: /eliminar|borrar|delete|sí|si/i }).last();
      if (await confirmar.count()) await confirmar.click().catch(() => undefined);
      await p.waitForTimeout(3000);
      const sigue = await p.evaluate(async (id) => {
        const t = localStorage.getItem('access_token');
        const r = await fetch(`/api/playlists/${id}`, { headers: { Authorization: 'Bearer ' + t } });
        return r.status;
      }, creada);
      ok('la lista se borra', sigue === 404, `la API responde ${sigue} (404 = borrada)`);
    } else {
      ok('el menú ofrece eliminar', false);
    }
  }

  ok('sin errores de JavaScript', errores.length === 0, errores.slice(0, 2).join(' | '));
  await p.screenshot({ path: 'ciclo-listas.png' });
  await b.close();
  const fallos = res.filter((r) => !r.bien);
  console.log(`\n================  ${res.length - fallos.length}/${res.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
