/*
 * Prueba de extremo a extremo de la REPRODUCCIÓN, contra el servidor de verdad.
 *
 * Se ejecuta en una pantalla de móvil emulada (390x844, táctil, sin ratón) porque es donde el
 * usuario escucha la música. Comprueba todo lo que se ha arreglado:
 *
 *   1. Se construye una playlist de prueba con canciones que SÍ tienen archivo en el servidor
 *      (el catálogo tiene más canciones que ficheros, y las que faltan devuelven 410).
 *   2. Reproducir esa playlist con el botón grande: que suene de verdad (el tiempo avanza) y que
 *      la interfaz no se caiga (antes lanzaba TypeError y la pantalla quedaba en blanco).
 *   3. Barra de progreso: que exista, avance y se pueda TOCAR para buscar (el componente
 *      anterior sólo escuchaba eventos de ratón: en táctil no hacía nada).
 *   4. Play/pausa: que pare Y vuelva a arrancar (antes sólo sabía pausar).
 *   5. Siguiente y anterior.
 *   6. Aleatorio: encender Y apagar (antes se quedaba encendido para siempre).
 *   7. Repetición: los tres estados.
 *   8. Volumen: que el deslizador cambie el volumen real del audio y se recuerde.
 *   9. Una canción sin archivo: que avise y salte a la siguiente en vez de quedarse clavada.
 *
 * Uso:  node probar-reproduccion.js        (URL por defecto: http://servidor:8090)
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = `repro-${Date.now()}@radiopv-test.com`;
const CLAVE = 'clave-de-pruebas-larga-123';

const resultados = [];
const comprobar = (nombre, ok, detalle = '') => {
  resultados.push({ nombre, ok, detalle });
  console.log(`  ${ok ? 'OK   ' : 'FALLO'}  ${nombre}${detalle ? `  ->  ${detalle}` : ''}`);
};

(async () => {
  const navegador = await chromium.launch({
    args: ['--autoplay-policy=user-gesture-required', '--mute-audio'],
  });
  const contexto = await navegador.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });

  // Enganchar el <audio> antes de que arranque la aplicación, y recoger los avisos en cuanto
  // aparecen: el mensaje de antd se desvanece a los pocos segundos y si se consulta el DOM
  // después, ya no está (falso negativo).
  await contexto.addInitScript(() => {
    window.__audio = null;
    const playOriginal = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (...a) {
      if (!window.__audio) window.__audio = this;
      return playOriginal.apply(this, a);
    };
    window.__avisos = [];
    const observar = () => {
      new MutationObserver(() => {
        // Aviso propio de la aplicación (el de las canciones sin archivo).
        const propio = document.querySelector('.radiopv-aviso');
        if (propio) {
          const t = (propio.textContent || '').trim();
          if (t && !window.__avisos.includes(t)) window.__avisos.push(t);
        }
        document.querySelectorAll('.ant-message-notice-content').forEach((n) => {
          const t = (n.textContent || '').trim();
          if (t && !window.__avisos.includes(t)) window.__avisos.push(t);
        });
      }).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
    };
    if (document.documentElement) observar();
    else document.addEventListener('DOMContentLoaded', observar);
  });

  const p = await contexto.newPage();
  const errores = [];
  const avisos = [];
  p.on('pageerror', (e) => {
    const t = String(e).split('\n')[0].slice(0, 160);
    if (!/play\(\) request was interrupted/i.test(t)) errores.push(t);
  });
  p.on('console', (m) => {
    if (m.type() === 'error') errores.push('consola: ' + m.text().slice(0, 160));
  });

  /** Estado real del audio de la aplicación. */
  const estado = () =>
    p.evaluate(() => {
      const a = window.__audio;
      const ms = navigator.mediaSession && navigator.mediaSession.metadata;
      return {
        hay: !!a,
        t: a ? Number(a.currentTime.toFixed(2)) : null,
        pausado: a ? a.paused : null,
        volumen: a ? a.volume : null,
        duracion: a ? Math.round(a.duration || 0) : 0,
        ready: a ? a.readyState : null,
        error: a && a.error ? a.error.code : null,
        src: a && a.src ? String(a.src).match(/stream\/(\d+)/)?.[1] : null,
        titulo: ms ? ms.title : null,
      };
    });

  /** Espera a que el reproductor esté realmente sonando (o devuelve el último estado).
   *  `distintoDe` obliga a esperar a que CAMBIE la canción: si no, se lee el estado de la
   *  canción anterior, que sigue sonando mientras la nueva carga. */
  const esperarSonido = async (ms = 12000, distintoDe = null) => {
    const fin = Date.now() + ms;
    let ultimo = await estado();
    while (Date.now() < fin) {
      const cambio = distintoDe === null || (ultimo.src && ultimo.src !== distintoDe);
      if (ultimo.hay && ultimo.pausado === false && ultimo.t > 0.5 && cambio) return ultimo;
      await p.waitForTimeout(400);
      ultimo = await estado();
    }
    return ultimo;
  };

  const avisosEnPantalla = () => p.evaluate(() => window.__avisos.slice());

  // --- sesión ---------------------------------------------------------------------------------
  console.log(`\n== Sesión en ${URL_BASE} ==`);
  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2500);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Repro');
  await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
  await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(6000);
  const dentro = !/inicia sesión para acceder/i.test(await p.evaluate(() => document.body.innerText));
  comprobar('sesión iniciada', dentro);
  if (!dentro) {
    await navegador.close();
    process.exit(1);
  }

  // --- 1. playlist de prueba con canciones que sí tienen archivo -------------------------------
  console.log('\n== Preparando una playlist con canciones reproducibles ==');
  const preparada = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const cab = { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' };
    const tok = await (await fetch('/api/auth/stream-token', { method: 'POST', headers: cab })).json();

    // Candidatas: se recorren canciones del catálogo hasta juntar cuatro que SÍ tengan archivo.
    // (El catálogo tiene más canciones que ficheros, así que hay que comprobarlo una a una.)
    const catalogo = await (await fetch('/api/tracks?limit=400', { headers: cab })).json();
    const buenas = [];
    let ausentes = 0;
    for (const c of catalogo) {
      const r = await fetch(`/api/stream/${c.id}?t=${encodeURIComponent(tok.token)}`, {
        headers: { Range: 'bytes=0-0' },
      });
      if (r.status === 206 || r.status === 200) buenas.push({ id: c.id, title: c.title });
      else ausentes++;
      if (buenas.length >= 5) break;
    }

    const nueva = await (
      await fetch('/api/playlists', {
        method: 'POST',
        headers: cab,
        body: JSON.stringify({ name: 'Prueba de reproducción', description: 'temporal' }),
      })
    ).json();
    for (const b of buenas) {
      await fetch(`/api/playlists/${nueva.id}/tracks/${b.id}`, { method: 'POST', headers: cab });
    }
    return { id: nueva.id, buenas, ausentes };
  });
  comprobar('hay canciones con archivo en el servidor', preparada.buenas.length >= 2, `${preparada.buenas.length} encontradas, ${preparada.ausentes} sin archivo`);
  // --- 2. reproducir la playlist ---------------------------------------------------------------
  console.log('\n== Reproducir la playlist ==');
  await p.goto(`${URL_BASE}/playlist/${preparada.id}`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4500);
  const grande = p.locator('button.circle-play.big').first();
  comprobar('la playlist tiene botón grande de reproducir', (await grande.count()) > 0);
  await grande.click({ timeout: 15000 });
  const e1 = await esperarSonido(15000);
  await p.waitForTimeout(500);
  const vivo = await p.evaluate(() => ({
    texto: document.body.innerText.length,
    fallo: document.body.innerText.includes('Algo ha fallado'),
  }));
  comprobar('la página sigue viva tras empezar a sonar (no se queda en blanco)', vivo.texto > 200 && !vivo.fallo, `${vivo.texto} caracteres`);
  comprobar('el botón grande pone música', e1.hay && e1.t > 0.5, `t=${e1.t}s, readyState=${e1.ready}`);
  comprobar('el audio no está en mudo', e1.volumen > 0, `volumen=${e1.volumen}`);
  comprobar('suena en la pantalla de bloqueo', !!e1.titulo, e1.titulo || 'sin metadatos');

  const t1 = e1.t;
  await p.waitForTimeout(3000);
  const e2 = await estado();
  comprobar('el tiempo avanza (suena de verdad)', e2.t > t1 + 1.5, `${t1}s -> ${e2.t}s`);

  // --- 3. pantalla "sonando ahora" del móvil ---------------------------------------------------
  console.log('\n== Pantalla completa del móvil ==');
  await p.locator('[aria-label="Abrir el reproductor"]').first().click();
  await p.waitForTimeout(1200);
  const hoja = p.locator('.mobile-now-playing');
  comprobar('se abre el reproductor a pantalla completa', (await hoja.count()) > 0);
  if (!(await hoja.count())) {
    console.log('  (sin esta pantalla no se pueden probar progreso, aleatorio ni repetición en el móvil)');
  }

  // --- 4. barra de progreso -------------------------------------------------------------------
  console.log('\n== Barra de progreso ==');
  const barra = hoja.locator('[role="slider"][aria-label="Barra de progreso"]').first();
  comprobar('existe la barra de progreso', (await barra.count()) > 0);
  if (await barra.count()) {
    const caja = await barra.boundingBox();
    comprobar('la barra es visible y tiene tamaño', !!caja && caja.width > 100, caja ? `${Math.round(caja.width)}x${Math.round(caja.height)}` : 'sin caja');
    if (caja) {
      // Toque al 70 %: en táctil el componente anterior no reaccionaba al dedo.
      await p.touchscreen.tap(caja.x + caja.width * 0.7, caja.y + caja.height / 2);
      await p.waitForTimeout(2500);
      const e3 = await estado();
      comprobar('tocar la barra busca dentro de la canción', e3.t > e2.t + 5, `de ${e2.t}s a ${e3.t}s (duración ${Math.round(e3.duracion / 1000)}s)`);
    }
  }

  // --- 5. play / pausa ------------------------------------------------------------------------
  console.log('\n== Play / pausa ==');
  const botonPlay = hoja.locator('button[aria-label="Pausar"], button[aria-label="Reproducir"]').first();
  comprobar('existe el botón de play/pausa en el móvil', (await botonPlay.count()) > 0);
  await botonPlay.click();
  await p.waitForTimeout(1500);
  const pausado = await estado();
  comprobar('el botón pausa', pausado.pausado === true, `pausado=${pausado.pausado}`);
  const etiqueta = await botonPlay.getAttribute('aria-label');
  comprobar('el botón pasa a "Reproducir" al pausar', etiqueta === 'Reproducir', `aria-label=${etiqueta}`);
  await botonPlay.click();
  await p.waitForTimeout(2500);
  const reanudado = await estado();
  comprobar('el botón vuelve a arrancar (antes sólo sabía pausar)', reanudado.pausado === false && reanudado.t > 0, `pausado=${reanudado.pausado}, t=${reanudado.t}s`);

  // --- 6. siguiente / anterior ----------------------------------------------------------------
  console.log('\n== Siguiente y anterior ==');
  const srcAntes = (await estado()).src;
  await hoja.locator('button[aria-label="Siguiente"]').first().click();
  const trasSig = await esperarSonido(15000, srcAntes);
  comprobar('"siguiente" cambia de canción y suena', trasSig.src !== srcAntes && trasSig.t > 0.5, `${srcAntes} -> ${trasSig.src}`);
  await hoja.locator('button[aria-label="Anterior"]').first().click();
  await p.waitForTimeout(4000);
  const trasAnt = await estado();
  // "Anterior" hace una de dos, y las dos son correctas (igual que Spotify): si llevas más de
  // 3 s vuelve a empezar la canción; si no, salta a la anterior del historial.
  const retrocedio = trasAnt.src !== trasSig.src || trasAnt.t < 2;
  comprobar('"anterior" retrocede (o reinicia la canción)', retrocedio, `${trasSig.src}(${trasSig.t}s) -> ${trasAnt.src}(${trasAnt.t}s)`);

  // --- 7. aleatorio ---------------------------------------------------------------------------
  console.log('\n== Aleatorio ==');
  const activoAleatorio = () => p.evaluate(() => !!document.querySelector('.mobile-now-playing button[aria-label="Barajar"] svg.active'));
  const aleatorio = hoja.locator('button[aria-label="Barajar"]').first();
  await aleatorio.click();
  await p.waitForTimeout(1000);
  const encendido = await activoAleatorio();
  await aleatorio.click();
  await p.waitForTimeout(1000);
  const apagado = await activoAleatorio();
  comprobar('el aleatorio se enciende', encendido === true, `activo=${encendido}`);
  // El botón mandaba "!shuffle" sobre un estado que siempre decía false: sólo se podía encender.
  comprobar('el aleatorio se puede APAGAR', apagado === false, `activo=${apagado}`);

  // --- 8. repetición --------------------------------------------------------------------------
  console.log('\n== Repetición ==');
  const estadoRepetir = () =>
    p.evaluate(() => {
      const svg = document.querySelector('.mobile-now-playing button[aria-label="Repetir"] svg');
      return svg ? { activo: svg.classList.contains('active'), una: svg.querySelectorAll('path').length >= 3 } : null;
    });
  const repetir = hoja.locator('button[aria-label="Repetir"]').first();
  const r0 = await estadoRepetir();
  await repetir.click();
  await p.waitForTimeout(900);
  const r1 = await estadoRepetir();
  await repetir.click();
  await p.waitForTimeout(900);
  const r2 = await estadoRepetir();
  await repetir.click();
  await p.waitForTimeout(900);
  const r3 = await estadoRepetir();
  const fmt = (r) => (r ? `${r.activo ? 'on' : 'off'}${r.una ? '+1' : ''}` : 'nulo');
  comprobar('repetir: apagado -> contexto', r1?.activo === true && r1?.una === false, `${fmt(r0)} -> ${fmt(r1)}`);
  comprobar('repetir: contexto -> una sola canción', r2?.activo === true && r2?.una === true, `${fmt(r1)} -> ${fmt(r2)}`);
  comprobar('repetir: vuelve a apagado', r3?.activo === false, `${fmt(r2)} -> ${fmt(r3)}`);

  // --- 9. volumen -----------------------------------------------------------------------------
  console.log('\n== Volumen ==');
  const vol = hoja.locator('[role="slider"][aria-label="Volumen"]').first();
  comprobar('existe la barra de volumen en el móvil', (await vol.count()) > 0);
  if (await vol.count()) {
    const cv = await vol.boundingBox();
    if (cv) {
      await p.touchscreen.tap(cv.x + cv.width * 0.4, cv.y + cv.height / 2);
      await p.waitForTimeout(1500);
      const ev = await estado();
      comprobar('tocar la barra de volumen cambia el volumen', ev.volumen > 0.15 && ev.volumen < 0.75, `volumen=${ev.volumen}`);
      const guardado = await p.evaluate(() => localStorage.getItem('radiopv_volume'));
      comprobar('el volumen se recuerda entre sesiones', guardado !== null, `guardado=${guardado}`);
    }
  }

  // --- 10. canción sin archivo: avisar y saltar, no quedarse clavada ---------------------------
  console.log('\n== Canción sin archivo (410) ==');
  const sinArchivo = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const cab = { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' };
    const tok = await (await fetch('/api/auth/stream-token', { method: 'POST', headers: cab })).json();
    const listas = await (await fetch('/api/playlists/system', { headers: cab })).json();
    const origen = [...listas].sort((a, b) => (b.n_tracks ?? 0) - (a.n_tracks ?? 0))[0];
    const candidatas = await (await fetch(`/api/playlists/${origen.id}/tracks`, { headers: cab })).json();
    const malas = [];
    for (const c of candidatas) {
      const r = await fetch(`/api/stream/${c.id}?t=${encodeURIComponent(tok.token)}`, { headers: { Range: 'bytes=0-0' } });
      if (r.status === 410 || r.status === 404) malas.push({ id: c.id, title: c.title });
      if (malas.length >= 1) break;
    }
    if (!malas.length) return null;
    // Playlist compuesta por una canción que falta.
    const nueva = await (await fetch('/api/playlists', { method: 'POST', headers: cab, body: JSON.stringify({ name: 'Prueba sin archivo' }) })).json();
    await fetch(`/api/playlists/${nueva.id}/tracks/${malas[0].id}`, { method: 'POST', headers: cab });
    return { playlist: nueva.id, cancion: malas[0] };
  });

  if (!sinArchivo) {
    comprobar('se encontró una canción sin archivo para probar', false, 'todas las probadas tienen archivo');
  } else {
    await p.goto(`${URL_BASE}/playlist/${sinArchivo.playlist}`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);
    await p.locator('button.circle-play.big').first().click();
    await p.waitForTimeout(4000);
    const mensajes = await avisosEnPantalla();
    const enPantalla = await p.evaluate(() => {
      const n = document.querySelector('.radiopv-aviso');
      return n ? (n.textContent || '').trim() : '';
    });
    const tras = await estado();
    // Antes: el elemento quedaba con paused=false, sin sonido y el tiempo en 0 para siempre.
    // Ahora: se avisa en pantalla y la reproducción no se queda bloqueada.
    const avisado = /no está en el servidor|No se pudo reproducir|faltan sus archivos/i.test(enPantalla + ' ' + mensajes.join(' '));
    comprobar('avisa en pantalla de que la canción no está en el servidor', avisado, enPantalla || mensajes.join(' | ') || 'sin aviso visible');
    comprobar('no se queda reproduciendo en falso sin sonar', !(tras.pausado === false && tras.t === 0), `pausado=${tras.pausado}, t=${tras.t}s, error=${tras.error}`);
    comprobar('la interfaz sigue viva', await p.evaluate(() => !document.body.innerText.includes('Algo ha fallado')));
  }

  // --- 11. sin errores graves -----------------------------------------------------------------
  console.log('\n== Errores ==');
  const graves = errores.filter((e) => !/favicon|ResizeObserver|DevTools|the server responded with a status of 4/i.test(e));
  comprobar('no hay errores de JavaScript', graves.length === 0, graves.slice(0, 3).join(' | ') || 'ninguno');

  const final = await estado();
  await p.screenshot({ path: 'reproduccion-movil.png' });

  const fallos = resultados.filter((r) => !r.ok);
  console.log(`\n================  ${resultados.length - fallos.length}/${resultados.length} comprobaciones OK  ================`);
  if (fallos.length) {
    console.log('FALLOS:');
    fallos.forEach((f) => console.log(`  · ${f.nombre}${f.detalle ? ` (${f.detalle})` : ''}`));
  }
  console.log(`estado final: "${final.titulo}" en ${final.t}s, volumen ${final.volumen}, error ${final.error}`);
  await navegador.close();
  process.exit(fallos.length ? 1 : 0);
})();
