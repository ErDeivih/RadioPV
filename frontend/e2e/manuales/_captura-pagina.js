/*
 * Captura UNA sola pantalla, en movil y en escritorio. Para comprobar un arreglo sin esperar a la
 * vuelta entera del reconocimiento visual (que son ~4 minutos).
 *
 * Uso: node _captura-pagina.js /importar
 *      node _captura-pagina.js /mix/radar solo-movil
 */
const { chromium } = require('playwright');
const fs = require('fs');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.CLAVE || 'clave-de-pruebas-larga-123';
const SALIDA = 'capturas';

const ruta = process.argv[2] || '/';
const soloMovil = (process.argv[3] || '').includes('movil');

(async () => {
  fs.mkdirSync(SALIDA, { recursive: true });
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const vistas = soloMovil
    ? [['movil', { width: 390, height: 844 }, true]]
    : [['movil', { width: 390, height: 844 }, true], ['escritorio', { width: 1440, height: 900 }, false]];

  for (const [vista, tamano, movil] of vistas) {
    const c = await b.newContext({ viewport: tamano, isMobile: movil, hasTouch: movil });
    const p = await c.newPage();
    p.on('pageerror', (e) => console.log('ERROR JS:', String(e).split('\n')[0].slice(0, 140)));

    await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(3500);

    let dentro = false;
    for (let i = 0; i < 3 && !dentro; i++) {
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
      dentro = await p.evaluate(async () => {
        const t = localStorage.getItem('access_token');
        if (!t) return false;
        const r = await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + t } });
        return r.ok;
      });
    }
    if (!dentro) {
      console.log(`FALLO: no se pudo entrar en ${vista}`);
      await c.close();
      continue;
    }

    await p.goto(URL_BASE + ruta, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4500);
    const archivo = `${SALIDA}/pagina-${ruta.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'inicio'}-${vista}.png`;
    await p.screenshot({ path: archivo });
    console.log('guardada', archivo);
    await c.close();
  }
  await b.close();
})();
