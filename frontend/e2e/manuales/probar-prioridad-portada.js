/*
 * ¿En qué orden salen las listas en la portada?
 *
 * POR QUÉ
 * -------
 * El usuario pidió PRIORIDAD para sesiones de DJ, mashups y cruces «canción A x canción B» («es lo
 * que escucho mucho»). Las listas ya existían, pero la portada las ordenaba sólo por número de
 * canciones, así que «Sesiones de DJ» —que tiene menos porque hay menos sesiones grabadas— se caía
 * de la fila y quedaba enterrada entre las demás.
 *
 * Ahora esas dos van primero. Esto lo comprueba mirando los títulos que se pintan, que es lo que ve
 * el usuario: una regla de orden que no se ve en pantalla no sirve de nada.
 *
 * Uso: node probar-prioridad-portada.js
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
  const c = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await c.newPage();

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4500);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2000);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Portada');
  await p.locator('input[placeholder="Email"]').first().fill(`portada-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(9000);

  // Los títulos de las listas que se ven en la portada, en orden de aparición.
  const listas = await p.evaluate(() =>
    [...document.querySelectorAll('.playlist-card')]
      .map((e) => (e.innerText || '').split('\n')[0].trim())
      .filter(Boolean)
  );
  console.log(`  listas en la portada: ${listas.slice(0, 8).join(' | ') || '(ninguna)'}`);

  const sitio = (nombre) => listas.findIndex((t) => t.toLowerCase().includes(nombre.toLowerCase()));
  const mashups = sitio('Mashups');
  const sesiones = sitio('Sesiones');

  ok('la portada enseña listas (no canciones sueltas)', listas.length >= 3, `${listas.length} listas`);
  ok('sale la lista de mashups y remixes', mashups >= 0, mashups >= 0 ? `posición ${mashups + 1}` : 'no sale');
  ok('sale la lista de sesiones de DJ', sesiones >= 0, sesiones >= 0 ? `posición ${sesiones + 1}` : 'no sale');
  ok('las dos salen en los DOS primeros puestos',
    mashups >= 0 && sesiones >= 0 && mashups < 2 && sesiones < 2,
    `mashups en ${mashups + 1}, sesiones en ${sesiones + 1}`);

  await b.close();
  const fallos = res.filter((r) => !r.bien);
  console.log(`\n================  ${res.length - fallos.length}/${res.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
