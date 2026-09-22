/*
 * Prueba de verdad del importador DESDE LA INTERFAZ: entra, va a /importar, pega el enlace de una
 * lista publica de Spotify, pulsa Importar y deja la captura del resultado.
 *
 * Uso: node _probar-importar.js [enlace-spotify]
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.CLAVE || 'clave-de-pruebas-larga-123';
const ENLACE = process.argv[2] || 'https://open.spotify.com/playlist/37i9dQZEVXbNFJfN1Vw8d9';

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage();
  p.on('pageerror', (e) => console.log('ERROR JS:', String(e).split('\n')[0].slice(0, 140)));

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(3500);
  for (let i = 0; i < 3; i++) {
    try {
      await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click({ timeout: 6000 });
      await p.waitForTimeout(1600);
      await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
      await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
      await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
      await p.waitForTimeout(5000);
    } catch (e) {
      await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
      await p.waitForTimeout(2000);
    }
    const ok = await p.evaluate(async () => {
      const t = localStorage.getItem('access_token');
      if (!t) return false;
      const r = await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + t } });
      return r.ok;
    });
    if (ok) break;
  }

  await p.goto(`${URL_BASE}/importar`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(3500);

  await p.locator('input[placeholder^="https://open.spotify.com"]').first().fill(ENLACE);
  await p.getByRole('button', { name: 'Importar' }).first().click();
  console.log('pulsado Importar; esperando a Spotify...');
  await p.waitForTimeout(15000);

  const texto = await p.evaluate(() => (document.querySelector('.importar-resultado')?.innerText || '').slice(0, 400));
  console.log('RESULTADO EN PANTALLA:\n' + (texto || '(vacío)'));
  await p.screenshot({ path: 'capturas/debug-importar-movil.png' });

  // Y la lista creada, abierta desde el propio resultado
  const enlaceLista = await p.locator(".importar-resultado a[href^='/playlist/']").first().getAttribute('href').catch(() => null);
  if (enlaceLista) {
    await p.goto(URL_BASE + enlaceLista, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(5000);
    await p.screenshot({ path: 'capturas/debug-importar-lista-movil.png' });
    console.log('lista guardada en capturas/debug-importar-lista-movil.png');
  }

  await b.close();
})();
