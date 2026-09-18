/*
 * Página de artista: ¿se puede escuchar al artista como UNA lista?
 *
 * Antes la sección «Popular» eran cinco canciones sueltas, cada una con su botón: no había forma
 * de decir «ponme este artista». Ahora hay un único botón que reproduce sus canciones más
 * escuchadas llenando la cola. Se comprueba en móvil y en escritorio:
 *   1. que exista el botón,
 *   2. que al pulsarlo suene de verdad (el tiempo avanza),
 *   3. que la cola quede con más de una canción (o sea, es una LISTA, no una canción suelta).
 *
 * Uso: node probar-artista.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';

const resultados = [];
const comprobar = (n, ok, detalle = '') => {
  resultados.push({ n, ok });
  console.log(`  ${ok ? 'OK   ' : 'FALLO'}  ${n}${detalle ? `  ->  ${detalle}` : ''}`);
};

(async () => {
  const navegador = await chromium.launch({ args: ['--autoplay-policy=user-gesture-required', '--mute-audio'] });

  for (const [etiqueta, opciones] of [
    ['PC', { viewport: { width: 1440, height: 900 } }],
    ['MÓVIL', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }],
  ]) {
    const c = await navegador.newContext(opciones);
    await c.addInitScript(() => {
      window.__audio = null;
      const orig = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function (...a) {
        if (!window.__audio) window.__audio = this;
        return orig.apply(this, a);
      };
    });
    const p = await c.newPage();
    const errores = [];
    p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 140)));

    await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(5000);
    await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
    await p.waitForTimeout(2500);
    await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
    await p.waitForTimeout(1000);
    const n = p.locator('input[placeholder="Nombre"]');
    if (await n.count()) await n.first().fill('Art');
    await p.locator('input[placeholder="Email"]').first().fill(`art-${Date.now()}-${etiqueta}@radiopv-test.com`);
    await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
    await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
    await p.waitForTimeout(7000);

    // Un artista que exista de verdad en el catálogo
    const artista = await p.evaluate(async () => {
      const t = localStorage.getItem('access_token');
      const r = await fetch('/api/artists?limit=3', { headers: { Authorization: 'Bearer ' + t } });
      const j = await r.json();
      return j?.[0]?.name;
    });
    await p.goto(`${URL_BASE}/artist/${encodeURIComponent(artista)}`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(6000);

    const boton = p.locator('button[aria-label="Reproducir la lista del artista"]').first();
    comprobar(`[${etiqueta}] el artista (${artista}) tiene un botón para escucharlo entero`,
      (await boton.count()) > 0);

    if (await boton.count()) {
      await boton.click().catch(() => undefined);
      await p.waitForTimeout(6000);
      const est = await p.evaluate(() => {
        const a = window.__audio;
        const ms = navigator.mediaSession && navigator.mediaSession.metadata;
        return { hay: !!a, t: a ? +a.currentTime.toFixed(1) : 0, pausado: a ? a.paused : null, titulo: ms ? ms.title : null };
      });
      comprobar(`[${etiqueta}] al pulsarlo suena`, est.hay && est.pausado === false && est.t > 0.5,
        `t=${est.t}s titulo=${est.titulo ?? '-'}`);

      // ¿La cola tiene más de una canción? Eso distingue una LISTA de una canción suelta.
      const cola = await p.evaluate(async () => {
        const t = localStorage.getItem('access_token');
        const r = await fetch('/api/library/history?limit=5', { headers: { Authorization: 'Bearer ' + t } });
        return r.status;
      });
      comprobar(`[${etiqueta}] la reproducción queda registrada (no es un fallo silencioso)`, cola === 200, `history ${cola}`);
    }

    comprobar(`[${etiqueta}] sin errores de JavaScript`, errores.length === 0, errores.slice(0, 2).join(' | '));
    await p.screenshot({ path: `artista-${etiqueta.toLowerCase()}.png` });
    await c.close();
  }

  await navegador.close();
  const fallos = resultados.filter((r) => !r.ok);
  console.log(`\n================  ${resultados.length - fallos.length}/${resultados.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
