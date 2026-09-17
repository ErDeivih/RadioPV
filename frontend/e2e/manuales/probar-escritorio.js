/*
 * Prueba del reproductor en ESCRITORIO (ratón, 1440x900).
 *
 * La barra de reproducción de escritorio es otra: aquí no se usa la pantalla del móvil, sino los
 * botones de la barra de abajo. Se comprueba que sigue todo bien después de reescribir el
 * deslizador, el contrato de estado y los controles.
 *
 * Uso:  node probar-escritorio.js
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = `escritorio-${Date.now()}@radiopv-test.com`;

const resultados = [];
const comprobar = (nombre, ok, detalle = '') => {
  resultados.push({ nombre, ok, detalle });
  console.log(`  ${ok ? 'OK   ' : 'FALLO'}  ${nombre}${detalle ? `  ->  ${detalle}` : ''}`);
};

(async () => {
  const navegador = await chromium.launch({
    args: ['--autoplay-policy=user-gesture-required', '--mute-audio'],
  });
  const contexto = await navegador.newContext({ viewport: { width: 1440, height: 900 } });
  await contexto.addInitScript(() => {
    window.__audio = null;
    const orig = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (...a) {
      if (!window.__audio) window.__audio = this;
      return orig.apply(this, a);
    };
    window.__avisos = [];
    const observar = () =>
      new MutationObserver(() => {
        const n = document.querySelector('.radiopv-aviso');
        if (n && n.textContent) window.__avisos.push(n.textContent.trim());
      }).observe(document.documentElement, { childList: true, subtree: true });
    if (document.documentElement) observar();
  });

  const p = await contexto.newPage();
  const errores = [];
  p.on('pageerror', (e) => {
    const t = String(e).split('\n')[0].slice(0, 160);
    if (!/play\(\) request was interrupted/i.test(t)) errores.push(t);
  });
  p.on('console', (m) => { if (m.type() === 'error' && !/410|404|Failed to load resource/i.test(m.text())) errores.push('consola: ' + m.text().slice(0, 160)); });

  const estado = () =>
    p.evaluate(() => {
      const a = window.__audio;
      const ms = navigator.mediaSession && navigator.mediaSession.metadata;
      return {
        t: a ? Number(a.currentTime.toFixed(2)) : null,
        pausado: a ? a.paused : null,
        volumen: a ? a.volume : null,
        src: a && a.src ? String(a.src).match(/stream\/(\d+)/)?.[1] : null,
        titulo: ms ? ms.title : null,
      };
    });

  const esperarSonido = async (ms = 15000, distintoDe = null) => {
    const fin = Date.now() + ms;
    let u = await estado();
    while (Date.now() < fin) {
      const cambio = distintoDe === null || (u.src && u.src !== distintoDe);
      if (u.t > 0.5 && u.pausado === false && cambio) return u;
      await p.waitForTimeout(400);
      u = await estado();
    }
    return u;
  };

  console.log(`\n== Sesión en ${URL_BASE} (escritorio) ==`);
  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2500);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Escritorio');
  await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
  await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(6000);
  comprobar('sesión iniciada', !/inicia sesión para acceder/i.test(await p.evaluate(() => document.body.innerText)));

  console.log('\n== Playlist con canciones reproducibles ==');
  const prep = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const cab = { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' };
    const tok = await (await fetch('/api/auth/stream-token', { method: 'POST', headers: cab })).json();
    const cat = await (await fetch('/api/tracks?limit=400', { headers: cab })).json();
    const buenas = [];
    for (const c of cat) {
      const r = await fetch(`/api/stream/${c.id}?t=${encodeURIComponent(tok.token)}`, { headers: { Range: 'bytes=0-0' } });
      if (r.status === 206 || r.status === 200) buenas.push(c.id);
      if (buenas.length >= 4) break;
    }
    const pl = await (await fetch('/api/playlists', { method: 'POST', headers: cab, body: JSON.stringify({ name: 'Escritorio' }) })).json();
    for (const b of buenas) await fetch(`/api/playlists/${pl.id}/tracks/${b}`, { method: 'POST', headers: cab });
    return { playlist: pl.id, cuantas: buenas.length };
  });
  comprobar('hay canciones reproducibles', prep.cuantas >= 2, `${prep.cuantas}`);

  console.log('\n== Reproducir y barra de abajo ==');
  await p.goto(`${URL_BASE}/playlist/${prep.playlist}`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4500);
  await p.locator('button.circle-play.big').first().click();
  const e1 = await esperarSonido();
  comprobar('el botón grande reproduce', e1.t > 0.5, `t=${e1.t}s`);
  comprobar('suena (no en mudo)', e1.volumen > 0, `volumen=${e1.volumen}`);
  comprobar('la interfaz no se ha caído', await p.evaluate(() => !document.body.innerText.includes('Algo ha fallado')));

  // La barra de escritorio: visible a 1440 px.
  const barra = p.locator('.mobile-hidden [role="slider"][aria-label="Barra de progreso"]').first();
  comprobar('la barra de progreso de escritorio es visible', await barra.isVisible().catch(() => false));
  const caja = await barra.boundingBox().catch(() => null);
  comprobar('tiene tamaño', !!caja && caja.width > 100, caja ? `${Math.round(caja.width)}x${Math.round(caja.height)}` : 'sin caja');
  if (caja) {
    const antes = (await estado()).t;
    // Arrastrar con el ratón hasta el 60 % (el caso que también se arregló para el dedo).
    await p.mouse.move(caja.x + caja.width * 0.6, caja.y + caja.height / 2);
    await p.mouse.down();
    await p.mouse.move(caja.x + caja.width * 0.75, caja.y + caja.height / 2, { steps: 8 });
    await p.mouse.up();
    await p.waitForTimeout(2500);
    const despues = (await estado()).t;
    comprobar('arrastrar con el ratón busca dentro de la canción', despues > antes + 5, `${antes}s -> ${despues}s`);
  }

  console.log('\n== Botones de la barra ==');
  const botonPlay = p.locator('.mobile-hidden button.player-pause-button').first();
  await botonPlay.click();
  await p.waitForTimeout(1200);
  comprobar('pausa', (await estado()).pausado === true);
  comprobar('el botón pasa a "Reproducir"', (await botonPlay.getAttribute('aria-label')) === 'Reproducir');
  await botonPlay.click();
  await p.waitForTimeout(2000);
  comprobar('vuelve a arrancar', (await estado()).pausado === false);

  const srcAntes = (await estado()).src;
  await p.locator('.mobile-hidden button[aria-label="Siguiente"]').first().click();
  const sig = await esperarSonido(15000, srcAntes);
  comprobar('siguiente cambia de canción', sig.src !== srcAntes, `${srcAntes} -> ${sig.src}`);
  await p.locator('.mobile-hidden button[aria-label="Anterior"]').first().click();
  await p.waitForTimeout(3500);
  const ant = await estado();
  comprobar('anterior retrocede o reinicia', ant.src !== sig.src || ant.t < 2, `${sig.src} -> ${ant.src} (${ant.t}s)`);

  const act = () => p.evaluate(() => !!document.querySelector('.mobile-hidden button[aria-label="Barajar"] svg.active'));
  await p.locator('.mobile-hidden button[aria-label="Barajar"]').first().click();
  await p.waitForTimeout(900);
  const on = await act();
  await p.locator('.mobile-hidden button[aria-label="Barajar"]').first().click();
  await p.waitForTimeout(900);
  const off = await act();
  comprobar('el aleatorio se enciende y se apaga', on === true && off === false, `${on} -> ${off}`);

  const rep = () =>
    p.evaluate(() => {
      const svg = document.querySelector('.mobile-hidden button[aria-label="Repetir"] svg');
      return svg ? { a: svg.classList.contains('active'), una: svg.querySelectorAll('path').length >= 3 } : null;
    });
  const r0 = await rep();
  await p.locator('.mobile-hidden button[aria-label="Repetir"]').first().click();
  await p.waitForTimeout(800);
  const r1 = await rep();
  await p.locator('.mobile-hidden button[aria-label="Repetir"]').first().click();
  await p.waitForTimeout(800);
  const r2 = await rep();
  comprobar('la repetición cicla', r1?.a === true && r1?.una === false && r2?.una === true, `${JSON.stringify(r0)} -> ${JSON.stringify(r1)} -> ${JSON.stringify(r2)}`);

  const vol = p.locator('.mobile-hidden [role="slider"][aria-label="Volumen"]').first();
  const cv = await vol.boundingBox().catch(() => null);
  if (cv) {
    await p.mouse.click(cv.x + cv.width * 0.3, cv.y + cv.height / 2);
    await p.waitForTimeout(1200);
    const ev = await estado();
    comprobar('la barra de volumen cambia el volumen', ev.volumen > 0.1 && ev.volumen < 0.7, `volumen=${ev.volumen}`);
  }

  console.log('\n== Errores ==');
  comprobar('sin errores de JavaScript', errores.length === 0, errores.slice(0, 3).join(' | ') || 'ninguno');

  await p.screenshot({ path: 'reproduccion-escritorio.png' });
  const fallos = resultados.filter((r) => !r.ok);
  console.log(`\n================  ${resultados.length - fallos.length}/${resultados.length} comprobaciones OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.nombre}${f.detalle ? ` (${f.detalle})` : ''}`));
  await navegador.close();
  process.exit(fallos.length ? 1 : 0);
})();
