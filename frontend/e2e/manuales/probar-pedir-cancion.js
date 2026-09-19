/*
 * La página de PEDIR CANCIONES, con toques reales, en móvil y en escritorio.
 *
 * POR QUÉ
 * -------
 * Es la página que pidió el usuario («una página en la app donde pedir una canción si no se
 * encuentra en la base propia y descargarla en la base») y la que antes era una caja de texto a
 * ciegas. Lo que hay que comprobar de verdad:
 *
 *   1. que al buscar salga lo que YA está en la biblioteca (con botón para oírlo), porque pedir algo
 *      que ya tienes es trabajo perdido;
 *   2. que salgan las versiones de YouTube CON su duración (para elegir: original, remix, directo…);
 *   3. que al pedir una se quede en «Mis peticiones» en estado «En cola»;
 *   4. y que se pueda usar con el dedo en un móvil (objetivos táctiles, nada cortado).
 *
 * Uso: node probar-pedir-cancion.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';
const CLAVE = 'clave-de-pruebas-larga-123';

const res = [];
const ok = (n, bien, detalle = '') => {
  res.push({ n, bien });
  console.log(`  ${bien ? 'OK   ' : 'FALLO'}  ${n}${detalle ? `  ->  ${detalle}` : ''}`);
};

/** Entra con un usuario nuevo (así no ensucia la cuenta de nadie). */
const entrar = async (p, etiqueta) => {
  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4500);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2000);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Pedir');
  await p.locator('input[placeholder="Email"]').first().fill(`pedir-${etiqueta}-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(7000);
};

/** Una canción que SÍ está en la biblioteca (se pregunta al buscador normal de la app). */
const cancionDeCasa = async (p) =>
  p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const r = await fetch('/api/tracks?limit=1', { headers: { Authorization: 'Bearer ' + t } });
    const d = await r.json();
    const tr = Array.isArray(d) ? d[0] : (d.items || [])[0];
    return tr ? { titulo: tr.title, artista: tr.artist } : null;
  });

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });

  for (const vista of [
    { nombre: 'móvil', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
    { nombre: 'escritorio', viewport: { width: 1440, height: 900 } },
  ]) {
    console.log(`\n--- ${vista.nombre} ---`);
    const c = await b.newContext({ ...vista, acceptDownloads: true });
    const p = await c.newPage();
    const errores = [];
    p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 130)));

    await entrar(p, vista.nombre);
    const casa = await cancionDeCasa(p);
    ok(`${vista.nombre}: hay catálogo con el que probar`, !!casa, casa ? `${casa.artista} - ${casa.titulo}` : 'vacío');

    // --- 1) Enlace en la barra de navegación ---
    // El nombre accesible del enlace es el del botón de dentro («Pedir una canción»), no el texto
    // visible («Pedir»): por eso se busca por /Pedir/ y no por el texto exacto.
    await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);
    const enlace = p.getByRole('link', { name: /Pedir/i }).first();
    ok(`${vista.nombre}: hay un enlace «Pedir» en la navegación`, (await enlace.count()) > 0);

    // --- 2) La página abre ---
    await p.goto(`${URL_BASE}/pedir`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);
    const titulo = await p.evaluate(() => document.body.innerText.slice(0, 160).replace(/\n/g, ' '));
    ok(`${vista.nombre}: la página abre y explica para qué es`,
      /pedir una canción/i.test(titulo), titulo.slice(0, 80));

    // --- 3) Buscar algo que YA está en casa ---
    const campo = p.locator('input[placeholder*="Bad Bunny"]').first();
    ok(`${vista.nombre}: hay campo de búsqueda`, (await campo.count()) > 0);
    if (!campo || !casa) {
      await c.close();
      continue;
    }
    await campo.fill(casa.titulo.slice(0, 18));
    await p.waitForTimeout(6000);

    const estado = await p.evaluate(() => {
      const texto = document.body.innerText;
      const botones = [...document.querySelectorAll('button')].map((b) => b.innerText.trim());
      return {
        yaEsta: texto.includes('ya está en tu biblioteca'),
        versiones: texto.includes('Versiones encontradas en YouTube'),
        escuchar: botones.filter((b) => /^Escuchar$/.test(b)).length,
        pedirEsta: botones.filter((b) => /Pedir esta/i.test(b)).length,
        duraciones: (texto.match(/\b\d{1,2}:\d{2}\b/g) || []).slice(0, 6),
      };
    });
    ok(`${vista.nombre}: avisa de lo que YA está en la biblioteca`, estado.yaEsta);
    ok(`${vista.nombre}: ofrece botón para oírlo en el momento`, estado.escuchar > 0,
      `${estado.escuchar} botones Escuchar`);
    ok(`${vista.nombre}: enseña versiones de YouTube`, estado.versiones || estado.pedirEsta > 0,
      `${estado.pedirEsta} versiones · duraciones: ${estado.duraciones.join(' ')}`);

    // --- 4) Pedir una versión concreta ---
    const pedirEsta = p.getByRole('button', { name: /Pedir esta/i }).first();
    if (await pedirEsta.count()) {
      await pedirEsta.click();
      await p.waitForTimeout(4000);
      const trasPedir = await p.evaluate(() => {
        const texto = document.body.innerText;
        return {
          enCola: texto.includes('En cola'),
          aviso: texto.includes('Pedida'),
        };
      });
      ok(`${vista.nombre}: al pedir una versión queda «En cola»`, trasPedir.enCola, trasPedir.aviso ? 'con aviso' : 'sin aviso');
    } else {
      ok(`${vista.nombre}: se puede pedir una versión concreta`, false, 'no hay resultados ahora mismo');
    }

    // --- 5) Comprobar en el servidor que la petición existe de verdad ---
    const guardadas = await p.evaluate(async () => {
      const t = localStorage.getItem('access_token');
      const r = await fetch('/api/requests', { headers: { Authorization: 'Bearer ' + t } });
      const d = await r.json();
      return Array.isArray(d) ? d.map((x) => x.status) : [];
    });
    ok(`${vista.nombre}: la petición está guardada en el servidor`, guardadas.length > 0,
      `${guardadas.length} peticiones: ${guardadas.join(', ')}`);

    // Los objetivos táctiles NO se miden aquí: los mide `probar-usabilidad.js`, que sabe calcular el
    // área efectiva (un botón puede medir 22 px y aun así acertarse en 44 por un pseudo-elemento) y
    // que además recorre todas las pantallas. Esta prueba mide lo funcional; la otra, el dedo.

    ok(`${vista.nombre}: sin errores de JavaScript`, errores.length === 0, errores.slice(0, 2).join(' | '));
    await p.screenshot({ path: `pedir-cancion-${vista.nombre}.png`, fullPage: false });
    await c.close();
  }

  await b.close();
  const fallos = res.filter((r) => !r.bien);
  console.log(`\n================  ${res.length - fallos.length}/${res.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
