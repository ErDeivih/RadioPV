/*
 * Comprobación de la fila «Hecho para ti»: cuántas tarjetas pinta el navegador de verdad, en qué
 * orden, y qué URL pide cada carátula del mosaico. Existe porque las capturas enseñaban las
 * carátulas ROTAS y tarjetas repetidas, y desde fuera no se sabe si el problema es de los datos o
 * del pintado.
 *
 * Uso: node _debug-mixes.js [--url http://servidor:8090]
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.CLAVE || 'clave-de-pruebas-larga-123';

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await c.newPage();
  p.on('pageerror', (e) => console.log('ERROR JS:', String(e).split('\n')[0]));

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(3000);
  try {
    await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click({ timeout: 5000 });
    await p.waitForTimeout(1500);
    await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
    await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
    await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
    await p.waitForTimeout(6000);
  } catch (e) {
    console.log('(aviso: login)', String(e).split('\n')[0].slice(0, 100));
  }

  // Lo que pide la aplicación al servidor, contado desde el propio navegador (con su sesión).
  const api = await p.evaluate(async () => {
    const r = await fetch('/api/mixes', { headers: { Authorization: 'Bearer ' + (localStorage.getItem('token') || '') } });
    const j = await r.json();
    return { status: r.status, n: Array.isArray(j) ? j.length : -1, kinds: Array.isArray(j) ? j.map((m) => m.kind) : j };
  });
  console.log('API /mixes →', JSON.stringify(api));

  const dom = await p.evaluate(() => {
    const tarjetas = [...document.querySelectorAll('.mix-card')];
    return {
      tarjetas: tarjetas.length,
      filas: document.querySelectorAll('.hecho-para-ti__fila').length,
      titulos: tarjetas.slice(0, 12).map((t) => t.querySelector('.mix-card__titulo')?.textContent),
      // las imágenes del mosaico de la primera tarjeta, tal cual las pide el navegador
      srcs: [...(tarjetas[0]?.querySelectorAll('.portada-mosaico img') || [])].map((i) => i.getAttribute('src')),
      cargadas: [...(tarjetas[0]?.querySelectorAll('.portada-mosaico img') || [])].map(
        (i) => i.complete && i.naturalWidth > 0
      ),
    };
  });
  console.log('DOM →', JSON.stringify(dom, null, 2));

  await b.close();
})();
