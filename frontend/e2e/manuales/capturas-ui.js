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
  // OJO: «Explorar» vive en /search (no hay /browse; esa ruta da la página 404)
  ['explorar', '/search'],
  ['buscar-resultados', '/search/Quevedo'],
  ['genero', '/genre/genre:techhouse'],
  ['genero-pop', '/genre/genre:pop'],
  ['artista', '/artist/Bad Bunny'],
  // Estas dos llevan LISTA/ALBUM como marca: sus ids no se escriben a mano (es lo que dejó la
  // captura del perfil en negro durante semanas), se leen del primer enlace que aparezca en la
  // pantalla anterior —la lista, de la portada; el álbum, de la página del artista—.
  ['lista', 'LISTA'],
  ['album', 'ALBUM'],
  ['discografia', '/artist/Bad Bunny/discography'],
  ['mis-canciones', '/users/PERFIL/tracks'],
  ['momentos', '/wrapped'],
  // «Hecho para ti»: la tarjeta del mix y la pantalla del mix (antes llevaban a /search y no había
  // ninguna pantalla donde ver el mix).
  ['mix-diario', '/mix/daily_1'],
  ['mix-radar', '/mix/radar'],
  ['mis-listas', '/users/PERFIL/playlists'],
  ['me-gusta', '/collection/tracks'],
  ['pedir', '/pedir'],
  ['ajustes', '/settings'],
  ['admin', '/admin'],
  // El perfil es el del usuario que ha iniciado sesión: el id se lee del enlace del avatar (antes
  // estaba a fuego `/users/1`, un id que ya no existe, así que la captura salía NEGRA y no se notó).
  ['perfil', '/users/PERFIL'],
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

    /** ¿Hay sesión de verdad? Se le pregunta a la API con el token del navegador.
     *
     *  POR QUÉ: entrar es un flujo con ventana y pestañas, y a veces falla (una vez de cada
     *  varias). Cuando fallaba, el script seguía y sacaba capturas de la aplicación SIN SESIÓN
     *  —pantallas vacías o con la ventana de «Iniciar sesión»— y esas capturas se revisaban como
     *  si fueran buenas. Es el mismo tipo de fallo que tuvo la captura del perfil en negro durante
     *  semanas: verificar mirando algo que no es lo que se cree. */
    const haySesion = async () =>
      p.evaluate(async () => {
        const token = localStorage.getItem('access_token');
        if (!token) return '';
        try {
          const r = await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + token } });
          if (!r.ok) return '';
          const j = await r.json();
          return String(j.id || '');
        } catch (e) {
          return '';
        }
      });

    const entrar = async () => {
      await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click({ timeout: 6000 });
      await p.waitForTimeout(1800);
      await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
      await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
      await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
      await p.waitForTimeout(6000);
    };

    let idPerfil = '';
    for (let intento = 1; intento <= 3 && !idPerfil; intento++) {
      try {
        await entrar();
      } catch (e) {
        console.log(`  (aviso: intento ${intento} de entrar falló: ${String(e).split('\n')[0].slice(0, 80)})`);
        await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
        await p.waitForTimeout(2500);
      }
      idPerfil = await haySesion();
    }
    if (!idPerfil) {
      // Sin sesión no se saca NADA de este tamaño: es mejor decir que no se ha verificado que
      // revisar capturas de una aplicación a la que no se ha entrado.
      console.log(`  FALLO: no se pudo entrar como ${EMAIL} en ${vista}; se omiten sus capturas`);
      await c.close();
      continue;
    }
    console.log(`  (sesión abierta: usuario ${idPerfil})`);

    // Los ids de lista y de álbum se leen del primer enlace de la pantalla correspondiente, en vez
    // de escribirlos a mano (que es justo lo que dejó la captura del perfil en negro semanas).
    let idLista = '';
    let idAlbum = '';

    for (const [nombre, rutaBase] of PANTALLAS) {
      let ruta = rutaBase.replace('PERFIL', idPerfil || '1');
      if (rutaBase === 'LISTA') {
        if (!idLista) {
          console.log('  (aviso: sin lista que capturar)');
          continue;
        }
        ruta = idLista;
      }
      if (rutaBase === 'ALBUM') {
        if (!idAlbum) {
          console.log('  (aviso: sin álbum que capturar)');
          continue;
        }
        ruta = idAlbum;
      }
      if (rutaBase.includes('PERFIL') && !idPerfil) continue;
      await p.goto(URL_BASE + ruta, { waitUntil: 'domcontentloaded' });
      await p.waitForTimeout(4500);
      // Un poco de scroll para que se vean también las filas de abajo
      await p.evaluate(() => window.scrollTo(0, 300));
      await p.waitForTimeout(1200);
      const archivo = `${SALIDA}/${vista}-${nombre}.png`;
      await p.screenshot({ path: archivo, fullPage: movil });
      const alto = await p.evaluate(() => document.body.scrollHeight);
      console.log(`  ${archivo.padEnd(38)} alto ${alto}px`);

      // De dónde salen los ids para las dos pantallas de arriba. La lista se pide a la API (las
      // tarjetas de la portada navegan con `onClick`, no llevan `href` que leer) y el álbum se lee
      // de un enlace real, que sí existe en las tablas de canciones.
      if (nombre === 'inicio' && !idLista) {
        idLista = await p.evaluate(async () => {
          const token = localStorage.getItem('access_token');
          const r = await fetch('/api/playlists/system', {
            headers: { Authorization: 'Bearer ' + token },
          });
          if (!r.ok) return '';
          const j = await r.json();
          return Array.isArray(j) && j.length ? '/playlist/' + j[0].id : '';
        });
      }
      if (!idAlbum) {
        const href = await p.evaluate(
          () => (document.querySelector('a[href^="/album/"]') || {}).getAttribute?.('href') || ''
        );
        if (href) idAlbum = href;
      }
    }
    if (errores.length) console.log(`  errores JS en ${vista}: ${errores.slice(0, 3).join(' | ')}`);
    await c.close();
  }

  await b.close();
  console.log(`\ncapturas en ${SALIDA}/`);
})();
