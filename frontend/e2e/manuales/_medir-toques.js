/*
 * Mide los objetivos TACTILES que se ven de verdad en el movil (botones, enlaces y lo que se toca),
 * y avisa de los que estan por debajo de 44 px. Solo cuenta lo VISIBLE: el medidor anterior contaba
 * tambien la barra de escritorio, que en el movil esta en el DOM pero no se ve, y por eso el numero
 * (251) no bajaba aunque se agrandaran los del reproductor del movil.
 *
 * Uso: node _medir-toques.js [/ruta]
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.CLAVE || 'clave-de-pruebas-larga-123';

const RUTAS = process.argv[2] ? [process.argv[2]] : ['/', '/search/Quevedo', '/mix/daily_1', '/collection/tracks', '/pedir', '/admin'];

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage();

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

  // Poner musica para que el reproductor del movil este en pantalla.
  await p.goto(`${URL_BASE}/`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(5000);
  try {
    await p.locator('.mix-card .circle-play').first().click({ timeout: 6000 });
    await p.waitForTimeout(7000);
  } catch (e) {
    console.log('(aviso: no se pudo poner musica)');
  }

  for (const ruta of RUTAS) {
    await p.goto(URL_BASE + ruta, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);
    const info = await p.evaluate(() => {
      const visible = (el) => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' &&
               Number(s.opacity) > 0.05 && r.bottom > 0 && r.top < window.innerHeight;
      };
      const nombre = (el) =>
        el.tagName.toLowerCase() +
        (typeof el.className === 'string' && el.className
          ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.')
          : '') +
        (el.getAttribute('aria-label') ? `[${el.getAttribute('aria-label')}]` : '');
      const todos = [...document.querySelectorAll('button, a, [role="button"], input, .ant-switch')];
      const pequenos = todos
        .filter(visible)
        .map((el) => ({ el: nombre(el), r: el.getBoundingClientRect() }))
        .filter((x) => x.r.width < 44 || x.r.height < 44)
        .map((x) => ({ el: x.el, w: Math.round(x.r.width), h: Math.round(x.r.height) }));
      return { visibles: todos.filter(visible).length, pequenos };
    });
    console.log(`\n== ${ruta} · ${info.visibles} controles visibles, ${info.pequenos.length} pequeños`);
    for (const q of info.pequenos.slice(0, 10)) console.log(`   ${q.w}x${q.h}  ${q.el}`);
  }

  await b.close();
})();
