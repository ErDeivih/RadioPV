/*
 * Auditoría de usabilidad y de "canciones sueltas", contra el servidor de verdad.
 *
 * Recorre las pantallas principales en MÓVIL (390x844 táctil) y en ESCRITORIO (1440x900) y mide,
 * en cada una:
 *   · CUANTAS CANCIONES SUELTAS se pintan (filas `.song-details`), porque el objetivo es que la
 *     interfaz ofrezca LISTAS y que la canción suelta aparezca sólo al entrar en una lista;
 *   · controles INVISIBLES (interactivos con opacidad 0, visibilidad oculta o tamaño cero): se
 *     pueden pulsar sólo si los ves, y en un móvil no hay ratón que los revele;
 *   · objetivos TÁCTILES pequeños (menos de 44x44 px, el mínimo recomendado para el dedo);
 *   · elementos RECORTADOS o que se salen de la pantalla por la derecha;
 *   · errores de JavaScript.
 *
 * No arregla nada: mide, y ordena los problemas para poder ir a por los peores.
 *
 * Uso: node probar-usabilidad.js [--url http://servidor:8090]
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const MINIMO_TACTIL = 44;   // px, en cualquiera de los dos lados

const inventario = [];

const anota = (vista, pantalla, datos) => {
  inventario.push({ vista, pantalla, ...datos });
  const sueltas = datos.cancionesSueltas;
  console.log(
    `  ${pantalla.padEnd(8)} ${vista.padEnd(26)} ` +
      `canciones=${String(sueltas).padEnd(3)} ` +
      `invisibles=${String(datos.invisibles.length).padEnd(3)} ` +
      `pequeños=${String(datos.pequenos.length).padEnd(3)} ` +
      `recortados=${String(datos.recortados.length).padEnd(3)} ` +
      `js=${datos.errores.length}`
  );
};

/** Mide una pantalla ya cargada. */
const medir = (p, vista) =>
  p.evaluate(
    ({ vista, minimo }) => {
      const visible = (el) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
        const s = getComputedStyle(el);
        return s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05;
      };

      /**
       * ¿Se puede PULSAR aunque no se vea? Eso es lo peligroso: un control con opacidad 0 sigue
       * recibiendo toques, así que en un móvil se activa sin querer al tocar "encima de nada".
       * Se comprueba de verdad, con `elementFromPoint` en el centro del elemento.
       *
       * OJO: sólo cuenta si el toque cae EN el elemento o en algo suyo de dentro. Antes también
       * daba por bueno el caso contrario (`arriba.contains(el)`, o sea que el que recibe el toque
       * es un PADRE), y eso es justo lo que NO queremos: con `pointer-events: none` el padre
       * recibe el clic y el botón está muerto, que es lo correcto. Esa regla de más marcaba como
       * "invisible y pulsable" todo botón inerte dentro de una fila.
       */
      const sePuedePulsar = (el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return false;
        const cx = Math.min(Math.max(r.left + r.width / 2, 1), window.innerWidth - 1);
        const cy = Math.min(Math.max(r.top + r.height / 2, 1), window.innerHeight - 1);
        const arriba = document.elementFromPoint(cx, cy);
        return !!arriba && (arriba === el || el.contains(arriba));
      };

      const interactivos = [
        ...document.querySelectorAll('button, a, [role="button"], input, select, textarea'),
      ];
      const nombre = (el) =>
        (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().slice(0, 44);
      const clase = (el) => String(el.className || '').slice(0, 46);

      // 1) Canciones sueltas que se ven en esta pantalla.
      const cancionesSueltas = [...document.querySelectorAll('.song-details')].filter(visible).length;

      // 2) Controles INVISIBLES pero pulsables. Es el fallo que más duele en el móvil.
      const invisibles = interactivos
        .filter((el) => !visible(el) && sePuedePulsar(el))
        .map((el) => ({ etiqueta: nombre(el), clase: clase(el) }));

      // 3) Objetivos táctiles pequeños.
      const pequenos = interactivos
        .filter(visible)
        .map((el) => {
          const r = el.getBoundingClientRect();
          return {
            etiqueta: nombre(el),
            clase: clase(el),
            w: Math.round(r.width),
            h: Math.round(r.height),
            y: Math.round(r.top),
            x: Math.round(r.left),
          };
        })
        .filter((x) => x.w < minimo || x.h < minimo);

      // 4) Recortes: cosas que se salen de la pantalla por la derecha, y desbordamiento horizontal.
      const ancho = window.innerWidth;
      const recortados = [...document.querySelectorAll('body *')]
        .filter(visible)
        .map((el) => ({ el, r: el.getBoundingClientRect() }))
        .filter(({ r }) => r.right > ancho + 2 && r.left < ancho)
        .slice(0, 6)
        .map(({ el, r }) => ({ etiqueta: nombre(el), clase: clase(el), seSale: Math.round(r.right - ancho) }));
      const desborda = document.documentElement.scrollWidth > ancho + 2;

      // 5) ¿Hay salida? Al menos un enlace o botón visible en la barra superior, para no quedarse
      //    encerrado en una pantalla sin forma de volver.
      const barra = document.querySelector('nav, header, .nav-header, [class*="navbar"]');
      const salidas = barra
        ? [...barra.querySelectorAll('a, button, [role="button"]')].filter(visible).length
        : 0;

      // 6) Textos que deberían estar en castellano y están en inglés. Se mira sólo el "cromo" de
      //    la interfaz (botones, títulos, etiquetas y los textos accesibles), nunca el contenido:
      //    el título de una canción puede llamarse "Home" y no es un fallo de traducción.
      const INGLES = [
        'Your Library', 'Recently played', 'Show more', 'Show less', 'Songs', 'Song',
        'Playlists', 'Albums', 'Artists', 'Top Result', 'Browse all', 'Followers',
        'Public Playlist', 'Private Playlist', 'Queue', 'Lyrics', 'Devices', 'Volume',
        'Mute', 'Shuffle', 'Repeat', 'Next', 'Previous', 'Cancel', 'Save', 'Delete',
        'Loading', 'No results', 'Search', 'Home', 'Settings', 'Expand your library',
        'Collapse your library', 'Log in', 'Log out', 'Sign up', 'Create a new Playlist',
        'Add to queue', 'Play', 'Pause',
      ];
      const cromo = [
        ...document.querySelectorAll(
          'button, h1, h2, h3, h4, label, [role="button"], .section-title, .playlist-header, .showMore'
        ),
      ].filter(visible);
      const enIngles = new Set();
      cromo.forEach((el) => {
        const trozos = [
          el.textContent || '',
          el.getAttribute('aria-label') || '',
          el.getAttribute('title') || '',
          el.getAttribute('placeholder') || '',
        ];
        trozos.forEach((texto) => {
          INGLES.forEach((palabra) => {
            // Palabra completa: "Home" sí, "Hometown" no.
            if (new RegExp(`(^|[^A-Za-zÁÉÍÓÚáéíóúñÑ])${palabra}([^A-Za-zÁÉÍÓÚáéíóúñÑ]|$)`).test(texto)) {
              enIngles.add(palabra);
            }
          });
        });
      });

      return {
        vista,
        cancionesSueltas,
        invisibles,
        pequenos,
        recortados,
        desborda,
        salidas,
        enIngles: [...enIngles],
      };
    },
    { vista, minimo: MINIMO_TACTIL }
  );

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  let fallos = 0;

  for (const pantalla of [
    { nombre: 'movil', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
    { nombre: 'escritorio', viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false },
  ]) {
    console.log(`\n================ ${pantalla.nombre.toUpperCase()} ================`);
    const c = await b.newContext({
      viewport: pantalla.viewport,
      isMobile: pantalla.isMobile,
      hasTouch: pantalla.hasTouch,
    });
    const p = await c.newPage();
    let errores = [];
    p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 120)));

    await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4500);
    // Sesión: la app pide login para casi todo.
    await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
    await p.waitForTimeout(2000);
    await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
    await p.waitForTimeout(800);
    const nom = p.locator('input[placeholder="Nombre"]');
    if (await nom.count()) await nom.first().fill('Usab');
    await p.locator('input[placeholder="Email"]').first().fill(`usab-${Date.now()}@radiopv-test.com`);
    await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
    await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
    await p.waitForTimeout(6000);

    // Datos reales para poder abrir un artista y un álbum que existan Y TENGAN MÚSICA. Si se
    // elige un artista con una sola canción, la auditoría mide una pantalla casi vacía y da una
    // falsa sensación de que todo está bien.
    const datos = await p.evaluate(async () => {
      const t = localStorage.getItem('access_token');
      const cab = { Authorization: 'Bearer ' + t };
      const pistas = await (await fetch('/api/tracks?limit=300', { headers: cab })).json();
      const cuenta = new Map();
      for (const x of pistas) cuenta.set(x.artist, (cuenta.get(x.artist) || 0) + 1);
      const mejor = [...cuenta.entries()].sort((a, b) => b[1] - a[1])[0];
      // El id del propio usuario, para poder auditar SU perfil (que es la biblioteca).
      let yo = null;
      try {
        yo = (await (await fetch('/api/auth/me', { headers: cab })).json())?.id ?? null;
      } catch {
        /* sin perfil */
      }
      // Un género que exista de verdad, para la página de género.
      let genero = null;
      try {
        const f = await (await fetch('/api/facets', { headers: cab })).json();
        genero = f?.genres?.[0]?.value ?? null;
      } catch {
        /* sin facetas */
      }
      return {
        artista: mejor ? mejor[0] : 'rosalia',
        cancionesDelArtista: mejor ? mejor[1] : 0,
        album: pistas[0]?.album ?? null,
        albumKey: pistas[0] && pistas[0].album ? `${pistas[0].artist}::${pistas[0].album}` : null,
        yo,
        genero,
      };
    });
    console.log(
      `  (artista de prueba: ${datos.artista} con ${datos.cancionesDelArtista} canciones en la ` +
        `muestra; álbum: ${datos.album ?? 'ninguno'}; género: ${datos.genero ?? 'ninguno'})`
    );

    const vistas = [
      ['Inicio', '/'],
      ['Explorar', '/search'],
      ['Buscar', `/search/${encodeURIComponent(datos.artista)}`],
      ['Artista', `/artist/${encodeURIComponent(datos.artista)}`],
      ['Álbum', datos.albumKey ? `/album/${encodeURIComponent(datos.albumKey)}` : '/'],
      ['Me gusta', '/collection/tracks'],
      ['Mis listas', '/users/1/playlists'],
      ['Ajustes', '/settings'],
      // El perfil es la biblioteca: ahí también se ofrecen listas.
      ['Perfil', datos.yo ? `/users/${datos.yo}` : '/'],
      ['Género', datos.genero ? `/genre/${encodeURIComponent(datos.genero)}` : '/'],
    ];

    for (const [nombre, ruta] of vistas) {
      errores = [];
      await p.goto(URL_BASE + ruta, { waitUntil: 'domcontentloaded' });
      await p.waitForTimeout(4500);
      const m = await medir(p, nombre);
      anota(ruta, pantalla.nombre, { ...m, errores });
    }

    await c.close();
  }

  await b.close();

  // ------------------------------------------------------------------ resumen
  console.log('\n================ RESUMEN ================');
  const conCanciones = inventario.filter((i) => i.cancionesSueltas > 0);
  if (conCanciones.length) {
    console.log('Pantallas que ofrecen CANCIONES SUELTAS (deberían ofrecer listas):');
    conCanciones.forEach((i) =>
      console.log(`   ${i.pantalla.padEnd(8)} ${i.vista.padEnd(26)} ${i.cancionesSueltas} filas`)
    );
  } else {
    console.log('Ninguna pantalla auditada ofrece canciones sueltas.');
  }

  const invisibles = inventario.filter((i) => i.invisibles.length > 0);
  if (invisibles.length) {
    console.log('\nControles INVISIBLES pero PULSABLES (se activan sin querer, porque no se ven):');
    const porClase = new Map();
    invisibles.forEach((i) =>
      i.invisibles.forEach((x) => {
        const k = `${x.clase}||${x.etiqueta}`;
        const e = porClase.get(k) || { clase: x.clase, etiqueta: x.etiqueta, pantallas: new Set() };
        e.pantallas.add(`${i.pantalla}/${i.vista}`);
        porClase.set(k, e);
      })
    );
    [...porClase.values()]
      .sort((a, b) => b.pantallas.size - a.pantallas.size)
      .forEach((e) =>
        console.log(
          `   [${e.pantallas.size} pantallas] ${(e.clase || e.etiqueta).slice(0, 52)}` +
            `   ·  ${[...e.pantallas].slice(0, 3).join(', ')}`
        )
      );
  }

  const ordenados = inventario
    .flatMap((i) => i.pequenos.map((x) => ({ ...x, pantalla: i.pantalla, vista: i.vista })))
    .sort((a, b) => a.w * a.h - b.w * b.h);
  console.log(`\nObjetivos táctiles pequeños (< ${MINIMO_TACTIL}px): ${ordenados.length} en total.`);
  const porClasePeques = new Map();
  ordenados.forEach((x) => {
    const k = x.clase || x.etiqueta;
    const e = porClasePeques.get(k) || { k, n: 0, min: x, vistas: new Set() };
    e.n += 1;
    if (x.w * x.h < e.min.w * e.min.h) e.min = x;
    e.vistas.add(x.vista);
    porClasePeques.set(k, e);
  });
  [...porClasePeques.values()]
    .sort((a, b) => b.n - a.n)
    .slice(0, 16)
    .forEach((e) =>
      console.log(
        `   ${String(e.n).padStart(3)}x  el más pequeño ${e.min.w}x${e.min.h}px  ` +
          `${e.k.slice(0, 46)}  ·  ${[...e.vistas].slice(0, 3).join(', ')}`
      )
    );

  const sinSalida = inventario.filter((i) => i.salidas === 0);
  if (sinSalida.length) {
    console.log('\nPantallas SIN forma visible de salir (callejón sin salida):');
    sinSalida.forEach((i) => console.log(`   ${i.pantalla.padEnd(8)} ${i.vista}`));
  }

  // Textos en inglés donde debería haber castellano de España.
  const ingles = new Map();
  inventario.forEach((i) =>
    (i.enIngles || []).forEach((palabra) => {
      const e = ingles.get(palabra) || new Set();
      e.add(`${i.pantalla}/${i.vista}`);
      ingles.set(palabra, e);
    })
  );
  if (ingles.size) {
    console.log('\nTextos en INGLÉS en el cromo de la interfaz (deberían ir en castellano):');
    [...ingles.entries()]
      .sort((a, b) => b[1].size - a[1].size)
      .forEach(([palabra, donde]) =>
        console.log(`   ${palabra.padEnd(28)} en ${donde.size} pantalla(s): ${[...donde].slice(0, 3).join(', ')}`)
      );
  } else {
    console.log('\nNingún texto en inglés en el cromo de las pantallas auditadas.');
  }

  // Detalle de los pequeños EN MÓVIL, con su posición: así se distingue la barra de abajo
  // (y > 700) de lo que está arriba (cabecera, tarjetas).
  const movilPeques = inventario
    .filter((i) => i.pantalla === 'movil')
    .flatMap((i) => i.pequenos.map((x) => ({ ...x, vista: i.vista })))
    .sort((a, b) => a.y - b.y || a.x - b.x);
  console.log(`\nDetalle en móvil (${movilPeques.length}), de arriba abajo:`);
  const vistos = new Set();
  movilPeques.forEach((x) => {
    const k = `${x.clase}|${x.w}x${x.h}|${x.vista}`;
    if (vistos.has(k)) return;
    vistos.add(k);
    const zona = x.y > 700 ? 'BARRA ABAJO' : x.y > 100 ? 'contenido' : 'cabecera';
    console.log(
      `   ${String(x.w).padStart(4)}x${String(x.h).padStart(3)}  y=${String(x.y).padStart(4)}  ` +
        `${zona.padEnd(11)} ${(x.clase || x.etiqueta).slice(0, 44)}  ·  ${x.vista}`
    );
  });

  const recortes = inventario.filter((i) => i.recortados.length > 0 || i.desborda);  if (recortes.length) {
    console.log('\nRecortes / desbordamiento horizontal:');
    recortes.forEach((i) =>
      console.log(
        `   ${i.pantalla.padEnd(8)} ${i.vista.padEnd(26)} desborda=${i.desborda} ` +
          i.recortados.slice(0, 3).map((r) => `${r.clase || r.etiqueta}(+${r.seSale}px)`).join(' ')
      )
    );
  }

  const conErrores = inventario.filter((i) => i.errores.length > 0);
  if (conErrores.length) {
    console.log('\nErrores de JavaScript:');
    conErrores.forEach((i) => console.log(`   ${i.pantalla} ${i.vista}: ${i.errores[0]}`));
  }

  fallos = conCanciones.length + invisibles.length + conErrores.length;
  process.exit(fallos ? 1 : 0);
})();
