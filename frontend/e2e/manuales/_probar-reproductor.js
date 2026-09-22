/*
 * Comprobacion del REPRODUCTOR, que no sale en las capturas normales porque hace falta tocar:
 *   1. poner a sonar un mix (boton de reproducir de la tarjeta),
 *   2. la barra de abajo,
 *   3. el panel de la cola,
 *   4. la vista de reproduccion (detalles) y la pantalla completa,
 *   5. en movil, el reproductor que se abre a pantalla completa.
 *
 * Uso: node _probar-reproductor.js
 */
const { chromium } = require('playwright');
const fs = require('fs');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.CLAVE || 'clave-de-pruebas-larga-123';
const SALIDA = 'capturas';

const pulsar = async (p, selector, etiqueta) => {
  try {
    const el = p.locator(selector).first();
    await el.click({ timeout: 6000 });
    await p.waitForTimeout(1800);
    console.log(`   ${etiqueta}: sí`);
    return true;
  } catch (e) {
    console.log(`   ${etiqueta}: NO (${String(e).split('\n')[0].slice(0, 70)})`);
    return false;
  }
};

(async () => {
  fs.mkdirSync(SALIDA, { recursive: true });
  const b = await chromium.launch({
    args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'],
  });

  for (const [vista, tamano, movil] of [
    ['movil', { width: 390, height: 844 }, true],
    ['escritorio', { width: 1440, height: 900 }, false],
  ]) {
    const c = await b.newContext({ viewport: tamano, isMobile: movil, hasTouch: movil });
    const p = await c.newPage();
    p.on('pageerror', (e) => console.log('   ERROR JS:', String(e).split('\n')[0].slice(0, 120)));

    await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);

    let dentro = false;
    for (let i = 0; i < 3 && !dentro; i++) {
      try {
        await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click({ timeout: 6000 });
        await p.waitForTimeout(1800);
        await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
        await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
        await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
        await p.waitForTimeout(6000);
      } catch (e) {
        await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
        await p.waitForTimeout(2500);
      }
      dentro = await p.evaluate(async () => {
        const t = localStorage.getItem('access_token');
        if (!t) return false;
        const r = await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + t } });
        return r.ok;
      });
    }
    if (!dentro) {
      console.log(`FALLO: no se pudo entrar en ${vista}; se omite`);
      await c.close();
      continue;
    }

    console.log(`== ${vista} ==`);
    await p.goto(`${URL_BASE}/`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(5000);

    // 1. Poner musica: boton de reproducir de la primera tarjeta de "Hecho para ti".
    await pulsar(p, '.mix-card .circle-play', 'poner a sonar un mix');
    await p.waitForTimeout(9000);

    // Que esta sonando de verdad (el estado lo publica el propio reproductor, y la barra de abajo
    // ensena el titulo). Las clases de la barra son `.song-title` y `.mobile-now-playing h2`.
    const sonando = await p.evaluate(() => {
      const t =
        document.querySelector('.song-title') ||
        document.querySelector('.mobile-now-playing .titulo h2') ||
        document.querySelector('.mobile-player .song-title');
      return (t?.textContent || '').trim().slice(0, 60);
    });
    console.log(`   suena: ${sonando || '(nada)'}`);
    await p.screenshot({ path: `${SALIDA}/debug-reproductor-barra-${vista}.png` });

    // 2. Panel de la cola / vista de reproduccion / pantalla completa.
    if (movil) {
      await pulsar(p, "[aria-label='Abrir el reproductor']", 'abrir el reproductor (movil)');
      await p.screenshot({ path: `${SALIDA}/debug-reproductor-completa-${vista}.png` });
      await pulsar(p, "[aria-label='Cola']", 'panel de la cola');
      await p.screenshot({ path: `${SALIDA}/debug-reproductor-cola-${vista}.png` });
    } else {
      await pulsar(p, "[aria-label='Cola']", 'panel de la cola');
      await p.screenshot({ path: `${SALIDA}/debug-reproductor-cola-${vista}.png` });
      await pulsar(p, "[aria-label='Cola']", 'cerrar la cola');
      await pulsar(p, "[aria-label='Vista de reproducción']", 'vista de reproduccion');
      await p.screenshot({ path: `${SALIDA}/debug-reproductor-detalles-${vista}.png` });
      await pulsar(p, "[aria-label='Vista de reproducción']", 'cerrar la vista');
      await pulsar(p, "[aria-label='Pantalla completa']", 'pantalla completa');
      await p.waitForTimeout(1200);
      await p.keyboard.press('Escape');
      await p.waitForTimeout(800);
    }

    await c.close();
  }

  await b.close();
  console.log(`\ncapturas en ${SALIDA}/debug-reproductor-*.png`);
})();
