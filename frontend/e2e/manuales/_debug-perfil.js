/*
 * Radiografia de la pagina de perfil: que elementos hay en la cabecera, donde estan y cual es el
 * que sale mal colocado. Existe porque en las capturas se veia un texto suelto arriba, un recuadro
 * cortado y un bloque gris vacio, y desde fuera no se sabe que elemento es cada cosa.
 *
 * Uso: node _debug-perfil.js
 */
const { chromium } = require('playwright');

const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.CLAVE || 'clave-de-pruebas-larga-123';

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  for (const [vista, tamano, movil] of [
    ['movil', { width: 390, height: 844 }, true],
    ['escritorio', { width: 1440, height: 900 }, false],
  ]) {
    const c = await b.newContext({ viewport: tamano, isMobile: movil, hasTouch: movil });
    const p = await c.newPage();
    p.on('pageerror', (e) =>
      console.log('ERROR JS:', String(e.stack || e).split('\n').slice(0, 4).join(' | ').slice(0, 400))
    );
    p.on('console', (m) => {
      if (m.type() === 'error') console.log('CONSOLA:', m.text().slice(0, 160));
    });
    await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(3000);
    try {
      await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click({ timeout: 5000 });
      await p.waitForTimeout(1500);
      await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
      await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
      await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
      await p.waitForTimeout(5000);
    } catch (e) {
      console.log('(aviso: login)', String(e).split('\n')[0].slice(0, 90));
    }

    const idPerfil = await p.evaluate(async () => {
      const token = localStorage.getItem('access_token') || localStorage.getItem('token') || '';
      const claves = Object.keys(localStorage);
      try {
        const r = await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + token } });
        const texto = await r.text();
        if (r.ok) {
          const j = JSON.parse(texto);
          if (j && j.id) return String(j.id);
        }
        console.log('DIAGNOSTICO me:', r.status, texto.slice(0, 120), 'claves:', claves.join(','));
      } catch (e) {
        console.log('DIAGNOSTICO me: fallo', String(e).slice(0, 120));
      }
      return '1';
    });
    await p.goto(`${URL_BASE}/users/${idPerfil}`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);

    const info = await p.evaluate(() => {
      const caja = (el) => {
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
      };
      const nombre = (el) =>
        el.tagName.toLowerCase() + (el.className && typeof el.className === 'string'
          ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.')
          : '');
      const cabecera = document.querySelector('.profile-header');
      const secciones = [...document.querySelectorAll('.grid-item-list-header, h1, h2')]
        .slice(0, 8)
        .map((el) => ({ el: nombre(el), texto: (el.textContent || '').trim().slice(0, 30), ...caja(el) }));
      // Todo lo que esté por encima del título y no sea la barra de arriba
      const sospechosos = [...document.querySelectorAll('.Main-section *')]
        .filter((el) => {
          const r = el.getBoundingClientRect();
          const t = (el.textContent || '').trim();
          return r.height > 0 && r.height < 60 && r.y > 60 && r.y < 160 && t.length > 0 && el.children.length <= 1;
        })
        .slice(0, 8)
        .map((el) => ({ el: nombre(el), texto: (el.textContent || '').trim().slice(0, 40), ...caja(el) }));
      return {
        idPerfil: location.pathname,
        cabecera: cabecera ? caja(cabecera) : null,
        hijosCabecera: cabecera ? [...cabecera.children].map((el) => ({ el: nombre(el), ...caja(el) })) : [],
        avatar: (() => {
          const img = document.querySelector('.profile-img img');
          return img ? { src: (img.getAttribute('src') || '').slice(-40), ...caja(img) } : null;
        })(),
        secciones,
        sospechosos,
        cuerpoAlto: document.querySelector('.Main-section')?.scrollHeight,
        texto: (document.querySelector('.Main-section')?.innerText || '').replace(/\s+/g, ' ').slice(0, 240),
      };
    });
    console.log(`\n=== ${vista} (${info.idPerfil}) ===`);
    await p.screenshot({ path: `capturas/debug-perfil-${vista}.png` });
    console.log('texto de la pagina:', info.texto);
    console.log('cabecera:', JSON.stringify(info.cabecera));
    console.log('hijos de la cabecera:', JSON.stringify(info.hijosCabecera, null, 1));
    console.log('avatar:', JSON.stringify(info.avatar));
    console.log('titulos/secciones:', JSON.stringify(info.secciones, null, 1));
    console.log('elementos sueltos arriba:', JSON.stringify(info.sospechosos, null, 1));
    await c.close();
  }
  await b.close();
})();
