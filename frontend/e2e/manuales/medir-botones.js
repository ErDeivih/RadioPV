/*
 * ¿Por qué un botón mide menos de 44 px en el móvil? Medición de verdad, no suposiciones.
 *
 * La auditoría (`probar-usabilidad.js`) dice que en la página de pedir canciones hay botones de
 * 40 px de alto. La regla del CSS pone 44 con `min-block-size`, así que hay que ver qué está
 * pasando: si la regla no se aplica (antd inyecta sus estilos DESPUÉS del CSS del proyecto y, a
 * igualdad de especificidad, gana el último), o si el elemento medido no es el botón.
 *
 * Uso: node medir-botones.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage();

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2000);
  await p.getByRole('button', { name: 'Registrarse', exact: true }).first().click();
  await p.waitForTimeout(1000);
  const n = p.locator('input[placeholder="Nombre"]');
  if (await n.count()) await n.first().fill('Medir');
  await p.locator('input[placeholder="Email"]').first().fill(`medir-${Date.now()}@radiopv-test.com`);
  await p.locator('input[placeholder="Contraseña"]').first().fill('clave-de-pruebas-larga-123');
  await p.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await p.waitForTimeout(7000);

  await p.goto(`${URL_BASE}/pedir`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4000);
  const campo = p.locator('input[placeholder*="Bad Bunny"]').first();
  if (await campo.count()) await campo.fill('Los Huesos');
  await p.waitForTimeout(5000);

  const datos = await p.evaluate(() =>
    [...document.querySelectorAll('button, a, input')]
      .filter((e) => e.offsetParent !== null)
      .map((e) => {
        const r = e.getBoundingClientRect();
        const cs = getComputedStyle(e);
        return {
          tag: e.tagName,
          clase: String(e.className || '').slice(0, 60),
          texto: (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 22),
          w: Math.round(r.width),
          h: Math.round(r.height),
          minH: cs.minHeight,
          minBlock: cs.minBlockSize,
          height: cs.height,
        };
      })
      .filter((x) => x.h > 0 && (x.w < 44 || x.h < 44))
  );

  console.log(`elementos pequeños (< 44 px) en /pedir: ${datos.length}`);
  for (const d of datos) {
    console.log(
      `   ${d.tag} ${d.w}x${d.h}  min-height=${d.minH} min-block-size=${d.minBlock} height=${d.height}  «${d.texto}»  ${d.clase}`
    );
  }

  await b.close();
})();
