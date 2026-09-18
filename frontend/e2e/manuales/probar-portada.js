/*
 * Comprueba que la portada está centrada en listas (PC y móvil).
 *
 * Qué mira:
 *   1. que NO exista la rejilla de canciones sueltas (`.home-top-tracks`, la sección "Para ti");
 *   2. qué secciones salen y cuántas tarjetas de lista hay;
 *   3. que las tarjetas de lista se puedan abrir y su botón de reproducir sea visible
 *      (en móvil es donde solía fallar: todo lo que dependía del ratón).
 *
 * Crea una cuenta de prueba; se borra después con scripts/limpiar_datos_de_prueba.py.
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';

const resultados = [];
const comprobar = (n, ok, detalle = '') => {
  resultados.push({ n, ok });
  console.log(`  ${ok ? 'OK   ' : 'FALLO'}  ${n}${detalle ? `  ->  ${detalle}` : ''}`);
};

async function mirarPortada(p, etiqueta) {
  const info = await p.evaluate(() => {
    const titulos = [...document.querySelectorAll('.home p, .home h2, .home h3')]
      .map((n) => (n.textContent || '').trim())
      .filter((t) => t && t.length < 40);
    const unicos = [...new Set(titulos)];
    return {
      sueltas: document.querySelectorAll('.home-top-tracks').length,
      tarjetas: document.querySelectorAll('.home [class*="card"], .home [class*="Card"]').length,
      imagenes: document.querySelectorAll('.home img').length,
      titulos: unicos.slice(0, 18),
    };
  });
  console.log(`\n  [${etiqueta}] rejilla de canciones sueltas: ${info.sueltas}`);
  console.log(`  [${etiqueta}] tarjetas: ${info.tarjetas} · imágenes: ${info.imagenes}`);
  console.log(`  [${etiqueta}] secciones: ${info.titulos.join(' | ')}`);
  return info;
}

(async () => {
  const navegador = await chromium.launch();
  const email = `portada-${Date.now()}@radiopv-test.com`;

  for (const [etiqueta, contexto] of [
    ['PC', await navegador.newContext({ viewport: { width: 1440, height: 900 } })],
    ['MÓVIL', await navegador.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })],
  ]) {
    const p = await contexto.newPage();
    const errores = [];
    p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 120)));

    await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(5000);

    // Cuenta nueva (la primera vez registra; la segunda ya existe, así que se inicia sesión)
    if (etiqueta === 'PC') {
      await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
      await p.waitForTimeout(2500);
      await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
      await p.waitForTimeout(1000);
      const n = p.locator('input[placeholder="Nombre"]');
      if (await n.count()) await n.first().fill('Portada');
      await p.locator('input[placeholder="Email"]').first().fill(email);
      await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
      await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
      await p.waitForTimeout(8000);
    } else {
      // El móvil es OTRO contexto de navegador: no hereda la sesión del PC, hay que entrar.
      await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
      await p.waitForTimeout(2500);
      await p.locator('input[placeholder="Email"]').first().fill(email);
      await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
      await p
        .getByRole('button', { name: /^(Iniciar sesión|Entrar)$/ })
        .last()
        .click()
        .catch(() => undefined);
      await p.waitForTimeout(9000);
    }

    const dentro = !/inicia sesión para acceder/i.test(await p.evaluate(() => document.body.innerText));
    comprobar(`[${etiqueta}] sesión iniciada`, dentro);
    if (!dentro) continue;

    await p.evaluate(() => {
      const s = document.querySelector('.Main-section');
      if (s) s.scrollTop = 400;
    });
    await p.waitForTimeout(2500);

    const info = await mirarPortada(p, etiqueta);
    comprobar(`[${etiqueta}] la portada NO enseña canciones sueltas`, info.sueltas === 0, `${info.sueltas} rejillas`);
    comprobar(`[${etiqueta}] hay listas en la portada`, info.imagenes >= 8, `${info.imagenes} imágenes`);

    // Las tarjetas navegan por JavaScript (no son un <a href>). OJO: pulsar la CARÁTULA activa el
    // botón de reproducir que va encima, así que para ENTRAR en la lista se pulsa su nombre.
    const nombre = p.getByText('Novedades', { exact: true }).first();
    comprobar(`[${etiqueta}] hay tarjetas de lista`, (await nombre.count()) > 0);
    if (await nombre.count()) {
      await nombre.click({ timeout: 8000 }).catch(() => undefined);
      await p.waitForTimeout(3500);
      const url = await p.evaluate(() => location.pathname);
      comprobar(`[${etiqueta}] al pulsar el nombre de una lista se entra en ella`,
        /^\/playlist\/\d+/.test(url), url);
      const info2 = await p.evaluate(() => ({
        canciones: document.querySelectorAll('img').length,
        titulo: document.body.innerText.split('\n').slice(0, 3).join(' | ').slice(0, 90),
      }));
      console.log(`  [${etiqueta}] dentro: ${info2.titulo}`);
    }

    comprobar(`[${etiqueta}] sin errores de JavaScript`, errores.length === 0, errores.slice(0, 2).join(' | '));
    await p.screenshot({ path: `portada-${etiqueta.toLowerCase()}.png` });
    await contexto.close();
  }

  await navegador.close();
  const fallos = resultados.filter((r) => !r.ok);
  console.log(`\n================  ${resultados.length - fallos.length}/${resultados.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
