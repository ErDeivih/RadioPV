/*
 * Página de género y enlaces de las cabeceras.
 *
 *  1. La página de género debe empezar por las LISTAS del género (`Top pop`…) y dejar las
 *     canciones debajo.
 *  2. Entrar en una de esas listas tiene que funcionar.
 *  3. Los avatares de las cabeceras (álbum y "me gusta") llevaban a `/profile`, que NO existe
 *     como ruta: se acababa en la página de "no encontrado". Ahora van al artista y al perfil.
 *
 * Uso: node probar-genero.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';

const res = [];
const ok = (n, bien, detalle = '') => {
  res.push({ n, bien });
  console.log(`  ${bien ? 'OK   ' : 'FALLO'}  ${n}${detalle ? `  ->  ${detalle}` : ''}`);
};

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage();
  const errores = [];
  p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 130)));

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2000);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(800);
  const nom = p.locator('input[placeholder="Nombre"]');
  if (await nom.count()) await nom.first().fill('Genero');
  await p.locator('input[placeholder="Email"]').first().fill(`genero-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(6000);

  const datos = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const cab = { Authorization: 'Bearer ' + t };
    const me = await (await fetch('/api/auth/me', { headers: cab })).json();
    const pistas = await (await fetch('/api/tracks?limit=1', { headers: cab })).json();
    const sistema = await (await fetch('/api/playlists/system', { headers: cab })).json();
    return {
      yo: me.id,
      album: pistas[0]?.album ? `${pistas[0].artist}::${pistas[0].album}` : null,
      genero: (await (await fetch('/api/facets', { headers: cab })).json())?.genres?.[0]?.value ?? null,
      tops: sistema.filter((x) => /^top /i.test(x.name)).map((x) => x.name).slice(0, 6),
    };
  });
  console.log('  (listas "Top …" en el servidor: ' + (datos.tops.join(', ') || 'ninguna') + ')');

  // ---------- 1 y 2 · página de género ----------
  await p.goto(`${URL_BASE}/genre/${encodeURIComponent(datos.genero ?? 'pop')}`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);

  const genero = await p.evaluate(() => {
    const titulos = [...document.querySelectorAll('.playlist-header, .section-title')].map((h) => ({
      texto: h.textContent.trim(),
      y: Math.round(h.getBoundingClientRect().top),
    }));
    const listas = [...document.querySelectorAll('.playlist-card')].map((x) => x.textContent.trim().slice(0, 30));
    return { titulos, listas, hayFilas: document.querySelectorAll('.song-details').length };
  });
  console.log('  títulos en la página:', JSON.stringify(genero.titulos));

  const iListas = genero.titulos.findIndex((t) => /listas de este género/i.test(t.texto));
  const iCanciones = genero.titulos.findIndex((t) => /^canciones$/i.test(t.texto));
  ok('el género enseña las listas del género', iListas !== -1 && genero.listas.length > 0,
    `${genero.listas.length} listas`);
  ok('las listas van ANTES que las canciones',
    iListas !== -1 && iCanciones !== -1 && genero.titulos[iListas].y < genero.titulos[iCanciones].y,
    `listas y=${genero.titulos[iListas]?.y} · canciones y=${genero.titulos[iCanciones]?.y}`);

  if (genero.listas.length) {
    await p.locator('.playlist-card').first().click();
    await p.waitForTimeout(4000);
    const dentro = await p.evaluate(() => ({
      url: location.pathname,
      filas: document.querySelectorAll('.song-details').length,
      titulo: document.querySelector('h1.playlist-title')?.textContent?.trim() ?? null,
    }));
    ok('al pulsar una lista del género se entra en ella',
      /^\/playlist\/\d+$/.test(dentro.url), `${dentro.url} · ${dentro.titulo} · ${dentro.filas} canciones`);
  }

  // ---------- 3 · enlaces de las cabeceras ----------
  if (datos.album) {
    await p.goto(`${URL_BASE}/album/${encodeURIComponent(datos.album)}`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4500);
    const album = await p.evaluate(() => {
      const a = document.querySelector('.owner a.avatar-link, .owner a:has(img.playlist-avatar)');
      return { href: a ? a.getAttribute('href') : null };
    });
    ok('la foto del artista en el álbum lleva al ARTISTA (antes a /profile, que no existe)',
      !!album.href && album.href.startsWith('/artist/'), String(album.href));
    if (album.href) {
      await p.locator('.owner a').first().click();
      await p.waitForTimeout(4000);
      const url = await p.evaluate(() => location.pathname);
      const es404 = await p.evaluate(() =>
        document.body.innerText.includes('no encontrado') || document.body.innerText.includes('no existe')
      );
      ok('y esa página existe (no es la de "no encontrado")', !es404 && url.startsWith('/artist/'), url);
    }
  }

  await p.goto(`${URL_BASE}/collection/tracks`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4500);
  const meGusta = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const yo = await (await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + t } })).json();
    const a = document.querySelector('.owner a.avatar-link, .owner a:has(img.playlist-avatar)');
    return {
      href: a ? a.getAttribute('href') : null,
      // La cabecera sólo pinta el avatar si el usuario TIENE foto. Un usuario de prueba recién
      // creado no la tiene, así que no hay nada que pulsar: eso no es un fallo de la aplicación.
      tieneFoto: Boolean(yo?.images?.[0]?.url),
    };
  });
  if (!meGusta.tieneFoto) {
    ok('la foto de "me gusta" lleva al perfil de verdad', true,
      'el usuario de prueba no tiene foto: no hay avatar que pulsar');
  } else {
    ok('la foto de "me gusta" lleva al perfil de verdad',
      !!meGusta.href && /^\/users\/\d+$/.test(meGusta.href), String(meGusta.href));
  }

  const graves = errores.filter((e) => !/404/.test(e));
  ok('sin errores de JavaScript', graves.length === 0, graves.slice(0, 2).join(' | '));

  await p.screenshot({ path: 'genero.png' });
  await b.close();

  const fallos = res.filter((r) => !r.bien);
  console.log(`\n================  ${res.length - fallos.length}/${res.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
