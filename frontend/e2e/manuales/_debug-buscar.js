/*
 * Radiografia de la pantalla de resultados de busqueda en movil: que elementos hay y donde estan,
 * para averiguar que ocupa el hueco vacio que sale entre las pestanas y "Resultado mas relevante".
 *
 * Uso: node _debug-buscar.js
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.CLAVE || 'clave-de-pruebas-larga-123';

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage();
  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(3000);

  // Entrar (y comprobar que se ha entrado)
  for (let i = 0; i < 3; i++) {
    try {
      await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click({ timeout: 6000 });
      await p.waitForTimeout(1500);
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

  await p.goto(`${URL_BASE}/search/Quevedo`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(6000);

  const info = await p.evaluate(() => {
    const nombre = (el) =>
      el.tagName.toLowerCase() +
      (typeof el.className === 'string' && el.className
        ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.')
        : '');
    const caja = (el) => {
      const r = el.getBoundingClientRect();
      return { y: Math.round(r.y), h: Math.round(r.height), w: Math.round(r.width), x: Math.round(r.x) };
    };
    const contenedor = document.querySelector('.Main-section');
    const hijos = contenedor ? [...contenedor.querySelectorAll('*')] : [];
    // Elementos altos que no ensenan texto: los sospechosos de ser el hueco
    const huecos = hijos
      .filter((el) => {
        const r = el.getBoundingClientRect();
        const texto = (el.textContent || '').trim();
        return r.height > 60 && r.height < 400 && r.y > 40 && r.y < 400 && texto.length === 0;
      })
      .slice(0, 10)
      .map((el) => ({ el: nombre(el), ...caja(el) }));
    // Y los que SI ensenan texto, para saber donde empieza cada seccion
    const conTexto = hijos
      .filter((el) => {
        const r = el.getBoundingClientRect();
        const t = (el.textContent || '').trim();
        return r.height > 0 && r.y > 40 && r.y < 500 && t.length > 0 && el.children.length === 0;
      })
      .slice(0, 12)
      .map((el) => ({ el: nombre(el), texto: (el.textContent || '').trim().slice(0, 26), ...caja(el) }));
    return { huecos, conTexto, alto: contenedor?.scrollHeight };
  });

  console.log('alto de la pagina:', info.alto);
  console.log('HUECOS (elementos altos sin texto):');
  for (const h of info.huecos) console.log('  ', JSON.stringify(h));
  console.log('TEXTO visible (primeras secciones):');
  for (const t of info.conTexto) console.log('  ', JSON.stringify(t));
  await p.screenshot({ path: 'capturas/debug-buscar-movil.png' });
  await b.close();
})();
