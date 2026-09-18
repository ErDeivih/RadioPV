/*
 * Ciclo de vida COMPLETO de una lista, en MÓVIL y por la INTERFAZ:
 * crear con canciones -> abrir -> menú -> RENOMBRAR -> comprobar -> PONER FOTO -> comprobar
 * -> REPRODUCIR -> BORRAR (con su confirmación) -> comprobar.
 *
 * Todo se hace con toques reales y cada paso se comprueba CONTRA LA API, no contra lo que dice
 * la pantalla: así se sabe si el cambio llegó de verdad al servidor. También se comprueba que
 * salen los avisos, porque durante un tiempo el servidor guardaba los cambios y en pantalla no
 * aparecía NADA (los avisos de antd no se pintaban con React 19).
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

// PNG de 2x2 (de sobra: el navegador lo recorta y lo reescala a 640 antes de subirlo).
const PNG_2X2 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGP8z8DAwMDAxMDAwMAABAAA//8DAAX+Av7q1s3sAAAAAElFTkSuQmCC',
  'base64'
);

(async () => {
  const b = await chromium.launch({ args: ['--autoplay-policy=user-gesture-required', '--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await c.addInitScript(() => {
    window.__audio = null;
    const orig = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (...a) {
      if (!window.__audio) window.__audio = this;
      return orig.apply(this, a);
    };
  });
  const p = await c.newPage();
  const errores = [];
  p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 130)));

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2500);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Ciclo');
  await p.locator('input[placeholder="Email"]').first().fill(`ciclo2-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(8000);

  // Lista CON canciones
  const id = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const cab = { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' };
    const pl = await (await fetch('/api/playlists', {
      method: 'POST', headers: cab, body: JSON.stringify({ name: 'Original de prueba' }),
    })).json();
    const ts = await (await fetch('/api/tracks?limit=4', { headers: cab })).json();
    for (const tr of ts) await fetch(`/api/playlists/${pl.id}/tracks/${tr.id}`, { method: 'POST', headers: cab });
    return pl.id;
  });

  const enApi = () =>
    p.evaluate(async (pid) => {
      const t = localStorage.getItem('access_token');
      const r = await fetch(`/api/playlists/${pid}`, { headers: { Authorization: 'Bearer ' + t } });
      if (r.status !== 200) return { estado: `HTTP ${r.status}` };
      const d = await r.json();
      return { estado: 'ok', nombre: d.name, portada: d.cover, publica: d.public };
    }, id);

  const abrirMenu = async () => {
    await p.locator('button[aria-label*="Más opciones"]').first().click({ timeout: 10000 });
    await p.waitForTimeout(1500);
  };

  // Los avisos de antd: si no se pintan, el usuario no sabe si el cambio se ha guardado.
  const verAviso = async (texto) => {
    for (let i = 0; i < 20; i++) {
      const hay = await p.evaluate(
        (t) => [...document.querySelectorAll('.ant-message-notice')].some((e) => e.innerText.includes(t)),
        texto
      );
      if (hay) return true;
      await p.waitForTimeout(250);
    }
    return false;
  };

  await p.goto(`${URL_BASE}/playlist/${id}`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);
  ok('la lista se crea con su nombre', (await enApi()).nombre === 'Original de prueba', (await enApi()).nombre);

  // --- RENOMBRAR ---
  await abrirMenu();
  const editar = p.getByText('Editar detalles', { exact: true }).first();
  ok('el menú ofrece "Editar detalles"', (await editar.count()) > 0);
  if (await editar.count()) {
    await editar.click();
    await p.waitForTimeout(2000);
    // El campo VISIBLE (dentro del formulario hay además un input oculto de ProForm).
    const campo = p.locator('.ant-modal input[type="text"]:visible').first();
    ok('se abre el diálogo con el nombre actual', (await campo.inputValue().catch(() => '')) === 'Original de prueba',
      await campo.inputValue().catch(() => '(sin campo)'));
    if (await campo.count()) {
      await campo.fill('Renombrada desde el móvil');
      await p.waitForTimeout(400);

      // --- FOTO DE LA LISTA ---
      const fichero = p.locator('.ant-modal input[type="file"]').first();
      const hayFichero = (await fichero.count()) > 0;
      ok('el diálogo deja elegir foto', hayFichero);
      if (hayFichero) await fichero.setInputFiles({ name: 'portada.png', mimeType: 'image/png', buffer: PNG_2X2 });
      await p.waitForTimeout(600);

      const guardar = p.locator('.ant-modal button:visible', { hasText: /^Guardar$/ }).first();
      if (await guardar.count()) await guardar.click();
      const aviso = await verAviso('Lista actualizada');
      ok('sale el aviso de "Lista actualizada"', aviso);
      await p.waitForTimeout(3500);

      const tras = await enApi();
      ok('el nombre NUEVO queda guardado en el servidor', tras.nombre === 'Renombrada desde el móvil', tras.nombre);
      // Se mira EL TÍTULO (h1), no un trozo de texto de la página: en el móvil la cabecera no
      // está en los primeros caracteres y la comprobación daba un falso fallo.
      const titulo = await p.evaluate(
        () => document.querySelector('h1.playlist-title')?.textContent?.trim() ?? '(sin título)'
      );
      ok('la pantalla repinta el nombre nuevo', titulo === 'Renombrada desde el móvil', titulo);
      ok('la FOTO de la lista se sube al servidor',
        typeof tras.portada === 'string' && tras.portada.startsWith('/media/covers/'), String(tras.portada));
      // Y que la imagen se VEA: no basta con que haya un <img> con esa dirección. La API devuelve
      // rutas `/media/...` y quien las sirve está detrás de `/api`; sin ese prefijo, nginx
      // devuelve el index.html de la aplicación (¡con un 200!) y la imagen aparece rota.
      const foto = await p.evaluate(() => {
        const i = [...document.querySelectorAll('img')].find((x) => x.src.includes('/media/covers/playlist-'));
        if (!i) return { hay: false };
        return { hay: true, src: i.src, cargada: i.complete && i.naturalWidth > 0, ancho: i.naturalWidth };
      });
      ok('la pantalla pide la foto por la ruta correcta (/api/media)',
        foto.hay && foto.src.includes('/api/media/covers/playlist-'), foto.src ?? '(no hay imagen)');
      ok('la foto nueva se CARGA de verdad en la pantalla',
        Boolean(foto.cargada), `ancho=${foto.ancho ?? 0}`);
    }
  }

  // --- PRIVACIDAD: el botón debe hacer algo de verdad ---
  await p.reload({ waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4500);
  await abrirMenu();
  const hacerPublica = p.getByText('Hacer pública', { exact: true }).first();
  ok('la lista privada ofrece "Hacer pública"', (await hacerPublica.count()) > 0);
  if (await hacerPublica.count()) {
    await hacerPublica.click();
    await p.waitForTimeout(3000);
    ok('el servidor guarda que ahora es PÚBLICA', (await enApi()).publica === true);
    await abrirMenu();
    const hacerPrivada = p.getByText('Hacer privada', { exact: true }).first();
    ok('el menú cambia a "Hacer privada" (antes ofrecía siempre lo mismo)',
      (await hacerPrivada.count()) > 0);
    if (await hacerPrivada.count()) {
      await hacerPrivada.click();
      await p.waitForTimeout(3000);
      ok('y se puede volver a privada', (await enApi()).publica === false);
    }
  }

  // --- REPRODUCIR ---
  const play = p.locator('.playlist-controls button[aria-label="Reproducir"]').first();
  if (await play.count()) {
    await play.click().catch(() => undefined);
    await p.waitForTimeout(6000);
    const est = await p.evaluate(() => {
      const a = window.__audio;
      const ms = navigator.mediaSession && navigator.mediaSession.metadata;
      return { t: a ? +a.currentTime.toFixed(1) : 0, pausado: a ? a.paused : null, titulo: ms ? ms.title : null };
    });
    ok('la lista se reproduce', est.pausado === false && est.t > 0.5, `t=${est.t}s ${est.titulo ?? ''}`);
  } else {
    ok('la lista tiene botón de reproducir', false);
  }

  // --- BORRAR, pero primero se comprueba que PREGUNTA ---
  await p.goto(`${URL_BASE}/playlist/${id}`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4500);
  await abrirMenu();
  const borrar = p.getByText('Eliminar la lista', { exact: true }).first();
  ok('el menú ofrece "Eliminar la lista"', (await borrar.count()) > 0);
  if (await borrar.count()) {
    await borrar.click();
    await p.waitForTimeout(1500);
    const confirmacion = p.locator('.ant-modal-confirm');
    ok('borrar PIDE CONFIRMACIÓN (antes borraba al primer toque)', (await confirmacion.count()) > 0);

    // Cancelar no debe borrar nada.
    const cancelar = p.locator('.ant-modal-confirm button', { hasText: /^Cancelar$/ }).first();
    if (await cancelar.count()) {
      await cancelar.click();
      await p.waitForTimeout(2000);
      ok('al cancelar la lista SIGUE existiendo', (await enApi()).estado === 'ok', (await enApi()).estado);
    }

    await abrirMenu();
    await p.getByText('Eliminar la lista', { exact: true }).first().click();
    await p.waitForTimeout(1500);
    await p.locator('.ant-modal-confirm button', { hasText: /^Eliminar$/ }).first().click();
    const avisoBorrado = await verAviso('Lista eliminada');
    ok('sale el aviso de "Lista eliminada"', avisoBorrado);
    await p.waitForTimeout(3000);
    const estado = await enApi();
    ok('la lista queda BORRADA en el servidor', estado.estado === 'HTTP 404', estado.estado);
  }

  const graves = errores.filter((e) => !/404/.test(e));
  ok('sin errores de JavaScript (aparte de 404 esperados)', graves.length === 0, graves.slice(0, 2).join(' | '));
  await p.screenshot({ path: 'ciclo-listas.png' });
  await b.close();

  const fallos = res.filter((r) => !r.bien);
  console.log(`\n================  ${res.length - fallos.length}/${res.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
