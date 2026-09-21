/*
 * Reconocimiento visual: capturas de TODAS las pantallas, en móvil y en escritorio.
 *
 * Para qué: para comparar la aplicación con Spotify hay que MIRARLA, no leer el código. Esto
 * recorre las pantallas principales, espera a que carguen las listas y guarda una captura de cada
 * una en `capturas/`. Después se revisan una a una.
 *
 * Uso: node capturas-ui.js [--url http://servidor:8090]
 */
const { chromium } = require('playwright');
const fs = require('fs');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.CLAVE || 'clave-de-pruebas-larga-123';
const SALIDA = 'capturas';

const PANTALLAS = [
  ['inicio', '/'],
  ['explorar', '/browse'],
  ['buscar', '/search'],
  ['genero', '/genre/genre:techhouse'],
  ['lista-sistema', '/genre/genre:pop'],
  ['mis-listas', '/users/1/playlists'],
  ['me-gusta', '/collection/tracks'],
  ['pedir', '/pedir'],
  ['ajustes', '/settings'],
  ['admin', '/admin'],
  ['perfil', '/users/1'],
];

(async () => {
  fs.mkdirSync(SALIDA, { recursive: true });
  const b = await chromium.launch({ args: ['--mute-audio'] });

  for (const [vista, tamano, movil] of [
    ['movil', { width: 390, height: 844 }, true],
    ['escritorio', { width: 1440, height: 900 }, false],
  ]) {
    const c = await b.newContext({ viewport: tamano, isMobile: movil, hasTouch: movil });
    const p = await c.newPage();
    const errores = [];
    p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 120)));

    await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);
    // Entrar (hace falta para las pantallas de listas y para el panel)
    try {
      await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click({ timeout: 5000 });
      await p.waitForTimeout(1500);
      await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
      await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
      await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
      await p.waitForTimeout(5000);
    } catch (e) {
      console.log(`  (aviso: no se pudo iniciar sesión: ${String(e).split('\n')[0].slice(0, 90)})`);
    }

    for (const [nombre, ruta] of PANTALLAS) {
      await p.goto(URL_BASE + ruta, { waitUntil: 'domcontentloaded' });
      await p.waitForTimeout(4500);
      // Un poco de scroll para que se vean también las filas de abajo
      await p.evaluate(() => window.scrollTo(0, 300));
      await p.waitForTimeout(1200);
      const archivo = `${SALIDA}/${vista}-${nombre}.png`;
      await p.screenshot({ path: archivo, fullPage: movil });
      const alto = await p.evaluate(() => document.body.scrollHeight);
      console.log(`  ${archivo.padEnd(38)} alto ${alto}px`);
    }
    if (errores.length) console.log(`  errores JS en ${vista}: ${errores.slice(0, 3).join(' | ')}`);
    await c.close();
  }

  await b.close();
  console.log(`\ncapturas en ${SALIDA}/`);
})();
