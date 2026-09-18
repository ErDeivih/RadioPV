/*
 * Radiografía de las páginas: ¿qué ofrece cada una, listas o canciones sueltas?
 *
 * Recorre las páginas que menciona el objetivo (Inicio, Buscar, artista, álbum, biblioteca) en
 * MÓVIL, y cuenta por página cuántas tarjetas de lista hay frente a cuántas canciones sueltas,
 * más señales de usabilidad (elementos que se salen de la pantalla, controles diminutos).
 *
 * Uso: node radiografia.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';

(async () => {
  const b = await chromium.launch();
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

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2500);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Radio');
  await p.locator('input[placeholder="Email"]').first().fill(`radio-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(8000);

  // Datos reales del catálogo para poder visitar un artista y un álbum
  const datos = await p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const cab = { Authorization: 'Bearer ' + t };
    const artistas = await (await fetch('/api/artists?limit=3', { headers: cab })).json();
    const tracks = await (await fetch('/api/tracks?limit=3', { headers: cab })).json();
    return { artista: artistas?.[0]?.name, album: tracks?.[0] };
  });
  console.log('artista de prueba:', datos.artista, '| álbum:', datos.album?.artist, '-', datos.album?.album);

  const analizar = async (etiqueta) => {
    await p.waitForTimeout(1500);
    const r = await p.evaluate(() => {
      const canciones = document.querySelectorAll('.song-title, .song-details').length;
      const tarjetas = document.querySelectorAll('img').length;
      const botonesPlay = document.querySelectorAll('[aria-label="Reproducir"], [aria-label="Pausar"]').length;
      // Elementos que se salen por la derecha o son diminutos (usabilidad táctil)
      const vw = window.innerWidth;
      let seSalen = 0;
      document.querySelectorAll('button, a, img').forEach((el) => {
        const b = el.getBoundingClientRect();
        if (b.width > 0 && (b.right > vw + 2 || b.left < -2)) seSalen++;
      });
      let diminutos = 0;
      document.querySelectorAll('button').forEach((el) => {
        const b = el.getBoundingClientRect();
        if (b.width > 0 && b.height > 0 && (b.width < 28 || b.height < 28)) diminutos++;
      });
      return { canciones, tarjetas, botonesPlay, seSalen, diminutos, texto: document.body.innerText.split('\n').slice(0, 4).join(' | ').slice(0, 80) };
    });
    console.log(`\n  [${etiqueta}]`);
    console.log(`     canciones sueltas: ${r.canciones}   imágenes/tarjetas: ${r.tarjetas}   botones de reproducir: ${r.botonesPlay}`);
    console.log(`     usabilidad móvil : ${r.seSalen} elementos se salen de pantalla · ${r.diminutos} botones < 28px`);
    console.log(`     primeros textos  : ${r.texto}`);
    return r;
  };

  const rutas = [
    ['Inicio', '/'],
    ['Explorar/Buscar', '/search'],
    ['Buscar texto', '/search/rosalia'],
    ['Artista', datos.artista ? `/artist/${encodeURIComponent(datos.artista)}` : null],
    ['Álbum', datos.album ? `/album/${encodeURIComponent(`${datos.album.artist}::${datos.album.album ?? ''}`)}` : null],
    ['Me gusta', '/collection/tracks'],
  ];

  const resumen = {};
  for (const [etiqueta, ruta] of rutas) {
    if (!ruta) continue;
    await p.goto(URL_BASE + ruta, { waitUntil: 'domcontentloaded' });
    resumen[etiqueta] = await analizar(etiqueta + ' ' + ruta);
  }

  await b.close();
  console.log('\n=== resumen (canciones sueltas por página) ===');
  Object.entries(resumen).forEach(([k, v]) => console.log(`   ${k.padEnd(20)} sueltas=${v.canciones}  tarjetas=${v.tarjetas}`));
})();
