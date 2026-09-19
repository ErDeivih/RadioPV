/*
 * Prueba de verdad de DESCARGAR UNA LISTA A UNA CARPETA.
 *
 * Comprueba los dos caminos, porque son distintos y los dos tienen que funcionar:
 *
 *   A) ESCRITORIO con elección de carpeta (Chrome/Edge): se sustituye `showDirectoryPicker` por
 *      una carpeta falsa que apunta lo que se escribe. Así se comprueba, sin diálogos nativos,
 *      que los ficheros se crean CON su nombre «Artista - Título.mp3» y CON bytes de audio
 *      dentro (no ficheros vacíos ni páginas de error).
 *
 *   B) MÓVIL / Firefox, donde no hay `showDirectoryPicker`: se quita esa función y se comprueba
 *      que la descarga sale por el camino normal del navegador (evento `download`), que es lo
 *      único que se puede hacer en un móvil sin app nativa.
 *
 * Se comprueba contra lo que llega al disco del navegador, no contra lo que dice la pantalla:
 * durante un tiempo estos botones decían «Descargadas 4 canciones» sin bajar nada.
 *
 * Uso: node probar-descarga-carpeta.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';

const res = [];
const ok = (n, bien, detalle = '') => {
  res.push({ n, bien });
  console.log(`  ${bien ? 'OK   ' : 'FALLO'}  ${n}${detalle ? `  ->  ${detalle}` : ''}`);
};

/** Firma de un mp3: ID3 o cabecera de trama. Sirve para saber que es audio y no una página de error. */
const esAudio = (cabecera) =>
  cabecera.startsWith('ID3') || (cabecera[0] === 0xff && (cabecera[1] & 0xe0) === 0xe0);

const CLAVE = 'clave-de-pruebas-larga-123';

/** Entra con un usuario nuevo y devuelve el id de una lista con 3 canciones reales. */
const preparar = async (p, etiqueta) => {
  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4500);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2000);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Descarga');
  await p.locator('input[placeholder="Email"]').first().fill(`descarga-${etiqueta}-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(8000);

  return p.evaluate(async () => {
    const t = localStorage.getItem('access_token');
    const cab = { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' };
    const pl = await (await fetch('/api/playlists', {
      method: 'POST',
      headers: cab,
      body: JSON.stringify({ name: 'Para bajar a la carpeta' }),
    })).json();
    if (!pl.id) return { error: JSON.stringify(pl).slice(0, 120) };
    const ts = await (await fetch('/api/tracks?limit=3', { headers: cab })).json();
    const bien = [];
    for (const tr of ts) {
      const r = await fetch(`/api/playlists/${pl.id}/tracks/${tr.id}`, { method: 'POST', headers: cab });
      if (r.ok) bien.push(`${tr.artists?.[0]?.name || tr.artist || ''} - ${tr.name || tr.title}`);
    }
    // Lo que DE VERDAD tiene la lista: la prueba no se fía de lo que diga la pantalla.
    const dentro = await (await fetch(`/api/playlists/${pl.id}/tracks`, { headers: cab })).json();
    return {
      id: pl.id,
      puestas: bien.length,
      enLista: Array.isArray(dentro) ? dentro.length : (dentro.items || []).length,
      nombres: bien,
      // Para poder diagnosticar sin adivinar: qué devolvió /tracks y qué tiene la lista.
      crudo: `ts=${Array.isArray(ts) ? ts.length : typeof ts} pl=${JSON.stringify(pl).slice(0, 60)} ` +
        `dentro=${Array.isArray(dentro) ? 'array' : typeof dentro}:${JSON.stringify(dentro).slice(0, 160)}`,
    };
  });
};

/** Abre el menú de la lista y pulsa «Descargar a una carpeta». */
const abrirDescarga = async (p) => {
  await p.locator('button[aria-label*="Más opciones"]').first().click({ timeout: 15000 });
  await p.waitForTimeout(1500);
  const opcion = p.getByText('Descargar a una carpeta', { exact: true }).first();
  const hay = (await opcion.count()) > 0;
  if (hay) {
    await opcion.click();
    await p.waitForTimeout(4000);
  }
  return hay;
};

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });

  // ================= A) ESCRITORIO: el usuario elige carpeta =================
  console.log('\n--- A) escritorio, eligiendo carpeta ---');
  {
    const c = await b.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
    await c.addInitScript(() => {
      // Carpeta falsa en lugar de la nativa: apunta lo escrito para poder revisarlo después.
      window.__escritos = [];
      window.showDirectoryPicker = async () => ({
        getFileHandle: async (nombre) => ({
          createWritable: async () => ({
            write: async (blob) => {
              const buf = new Uint8Array(await blob.arrayBuffer());
              window.__escritos.push({
                nombre,
                bytes: buf.length,
                cabecera: String.fromCharCode(...buf.slice(0, 3)),
                primeros: [buf[0], buf[1]],
              });
            },
            close: async () => undefined,
          }),
        }),
      });
    });
    const p = await c.newPage();
    const errores = [];
    p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 130)));

    const lista = await preparar(p, 'pc');
    ok('la lista de prueba se crea con 3 canciones', lista.enLista === 3,
      `enLista=${lista.enLista} puestas=${lista.puestas} ${lista.crudo || lista.error || ""}`);
    await p.goto(`${URL_BASE}/playlist/${lista.id}`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(5000);

    ok('el menú de la lista ofrece "Descargar a una carpeta"', await abrirDescarga(p));

    const textoModal = await p.evaluate(() => {
      const m = document.querySelector('.ant-modal-content');
      return m ? m.innerText.replace(/\n/g, ' ') : '';
    });
    ok('el diálogo explica que se elegirá la carpeta', /carpeta donde guardarlas/i.test(textoModal),
      textoModal.slice(0, 110));
    ok('el diálogo cuenta las canciones de ESA lista (3)',
      new RegExp(`^${3} canciones`).test(textoModal.trim()) || textoModal.includes('3 canciones'),
      textoModal.slice(0, 60));

    const boton = p.getByRole('button', { name: /Elegir carpeta y descargar/i }).first();
    ok('el botón dice "Elegir carpeta y descargar"', (await boton.count()) > 0);

    if (await boton.count()) {
      await boton.click();
      // 3 canciones, con 400 ms de espera entre descargas en el otro camino: margen de sobra.
      for (let i = 0; i < 40; i++) {
        const listo = await p.evaluate(() => {
          const m = document.querySelector('.ant-modal-content');
          return m ? /3\/3/.test(m.innerText) || /Descargadas 3 canciones/.test(document.body.innerText) : false;
        });
        if (listo) break;
        await p.waitForTimeout(1000);
      }
    }

    const escritos = await p.evaluate(() => window.__escritos || []);
    ok('se escribieron 3 ficheros en la carpeta elegida', escritos.length === 3,
      `${escritos.length}: ${escritos.map((e) => e.nombre).join(' | ')}`);
    ok('los nombres son "Artista - Título.mp3"',
      escritos.length > 0 && escritos.every((e) => /\.mp3$/.test(e.nombre) && e.nombre !== '-.mp3' && /\S/.test(e.nombre.replace(/\.mp3$/, ''))),
      escritos.map((e) => e.nombre).join(' | '));
    ok('los ficheros llevan audio dentro (no están vacíos)',
      escritos.length > 0 && escritos.every((e) => e.bytes > 10240),
      escritos.map((e) => `${e.nombre}=${e.bytes}B`).join(' | '));
    ok('lo escrito es un mp3 de verdad',
      escritos.length > 0 && escritos.every((e) => esAudio(e.cabecera) || esAudio(String.fromCharCode(e.primeros[0], e.primeros[1]))),
      escritos.map((e) => `${e.cabecera}/${e.primeros.join(',')}`).join(' | '));

    const aviso = await p.evaluate(() => document.body.innerText.includes('Descargadas 3 canciones'));
    ok('avisa de que se han descargado las 3', aviso);
    ok('sin errores de JavaScript', errores.length === 0, errores.slice(0, 2).join(' | '));

    await p.screenshot({ path: 'descarga-carpeta-escritorio.png' });
    await c.close();
  }

  // ================= B) MÓVIL: no se puede elegir carpeta =================
  console.log('\n--- B) móvil, sin elección de carpeta ---');
  {
    const c = await b.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      acceptDownloads: true,
    });
    await c.addInitScript(() => {
      // En el móvil esa función no existe: hay que comprobar el otro camino.
      delete window.showDirectoryPicker;
      window.showDirectoryPicker = undefined;
    });
    const p = await c.newPage();
    const errores = [];
    const bajados = [];
    p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 130)));
    p.on('download', async (d) => {
      const ruta = await d.path().catch(() => null);
      let bytes = 0;
      let cabecera = '';
      if (ruta) {
        const fs = require('fs');
        const buf = fs.readFileSync(ruta);
        bytes = buf.length;
        cabecera = buf.slice(0, 3).toString('latin1');
      }
      bajados.push({ nombre: d.suggestedFilename(), bytes, cabecera });
    });

    const lista = await preparar(p, 'movil');
    ok('la lista de prueba se crea con 3 canciones', lista.enLista === 3,
      `enLista=${lista.enLista} puestas=${lista.puestas} ${lista.crudo || lista.error || ""}`);
    await p.goto(`${URL_BASE}/playlist/${lista.id}`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(5000);

    ok('el menú de la lista ofrece "Descargar a una carpeta"', await abrirDescarga(p));

    const textoModal = await p.evaluate(() => {
      const m = document.querySelector('.ant-modal-content');
      return m ? m.innerText.replace(/\n/g, ' ') : '';
    });
    ok('avisa de que no se puede elegir carpeta y va a Descargas',
      /no deja elegir carpeta/i.test(textoModal) && /Descargas/i.test(textoModal),
      textoModal.slice(0, 130));
    ok('el diálogo cuenta las canciones de ESA lista (3)', textoModal.includes('3 canciones'),
      textoModal.slice(0, 60));

    const boton = p.getByRole('button', { name: /^Descargar$/ }).first();
    ok('el botón dice "Descargar" (sin prometer carpeta)', (await boton.count()) > 0);

    if (await boton.count()) {
      await boton.click();
      for (let i = 0; i < 60 && bajados.length < 3; i++) await p.waitForTimeout(1000);
    }

    ok('el navegador recibió 3 descargas', bajados.length === 3,
      `${bajados.length}: ${bajados.map((d) => d.nombre).join(' | ')}`);
    ok('los nombres de fichero son correctos',
      bajados.length > 0 && bajados.every((d) => /\.mp3$/.test(d.nombre) && d.nombre !== '-.mp3'),
      bajados.map((d) => d.nombre).join(' | '));
    ok('las descargas traen audio de verdad',
      bajados.length > 0 && bajados.every((d) => d.bytes > 10240 && (esAudio(d.cabecera) || d.cabecera === '')),
      bajados.map((d) => `${d.nombre}=${d.bytes}B/${d.cabecera}`).join(' | '));
    ok('sin errores de JavaScript', errores.length === 0, errores.slice(0, 2).join(' | '));

    await p.screenshot({ path: 'descarga-carpeta-movil.png' });
    await c.close();
  }

  await b.close();

  const fallos = res.filter((r) => !r.bien);
  console.log(`\n================  ${res.length - fallos.length}/${res.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
