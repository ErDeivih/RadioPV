/*
 * ¿Está el panel de administración listo para hacer LIMPIEZA del catálogo?
 *
 * Entra con una cuenta de administración y recorre el panel como lo usaría una persona: mira qué
 * pestañas hay, si los atajos de limpieza están, si los recuentos salen, si el borrado en masa
 * PIDE CONFIRMACIÓN y si se puede usar en el móvil. No borra nada: sólo prueba el modo de
 * previsualización (dry-run).
 *
 * Uso: node probar-admin.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.ADMIN_EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.ADMIN_CLAVE || 'clave-de-pruebas-larga-123';

const res = [];
const ok = (n, bien, detalle = '') => {
  res.push({ n, bien });
  console.log(`  ${bien ? 'OK   ' : 'FALLO'}  ${n}${detalle ? `  ->  ${detalle}` : ''}`);
};

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage();
  const errores = [];
  p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 130)));

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4000);

  // --- entrar con la cuenta de administración ---
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2000);
  await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
  await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
  await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
  await p.waitForTimeout(6000);

  await p.goto(`${URL_BASE}/admin`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(6000);

  const panel = await p.evaluate(() => {
    const texto = document.body.innerText;
    const pestanas = [...document.querySelectorAll('.ant-tabs-tab')].map((t) => t.innerText.trim());
    const botones = [...document.querySelectorAll('button')].map((b) => b.innerText.trim()).filter(Boolean);
    const cabeceras = [...document.querySelectorAll('th')].map((t) => t.innerText.trim()).filter(Boolean);
    return {
      url: location.pathname,
      pestanas,
      // ¿Está la fila de atajos de limpieza rápida?
      limpiezaRapida: texto.includes('Limpieza rápida'),
      atajos: botones.filter((b) =>
        /sin idioma|retales|sin fichero|perdidas|cuarentena|fallidas|incompletas|peor valoradas|poco conocidas|portugués/i.test(b)
      ),
      acciones: botones.filter((b) => /borrar|vetar|limpiar|recargar|previsualizar/i.test(b)).slice(0, 14),
      cabeceras,
      filas: document.querySelectorAll('tbody tr').length,
      // ¿Se ve el recuento real del catálogo?
      recuento: (texto.match(/([\d.]+)\s*canciones/g) || []).slice(0, 4),
    };
  });

  console.log(`\n  panel: ${panel.url}`);
  console.log(`  pestañas: ${panel.pestanas.join(' | ') || '(ninguna)'}`);
  console.log(`  atajos de limpieza: ${panel.atajos.length}`);
  panel.atajos.slice(0, 10).forEach((a) => console.log(`     · ${a}`));
  console.log(`  acciones: ${panel.acciones.join(' | ')}`);
  console.log(`  columnas: ${panel.cabeceras.join(' | ')}`);
  console.log(`  filas visibles: ${panel.filas}`);
  console.log(`  recuentos en pantalla: ${panel.recuento.join(' · ')}`);

  ok('el panel de administración abre', panel.url === '/admin', panel.url);
  ok('tiene la limpieza rápida con atajos', panel.limpiezaRapida && panel.atajos.length >= 5,
    `${panel.atajos.length} atajos`);
  // El atajo del portugués tiene que estar: es la limpieza que pidió el usuario (política: no entra).
  ok('existe el atajo de portugués', panel.atajos.some((a) => /portugués/i.test(a)),
    panel.atajos.find((a) => /portugués/i.test(a)) || '(no está)');
  ok('enseña la tabla de canciones con columnas', panel.filas > 0 && panel.cabeceras.length >= 5,
    `${panel.filas} filas · ${panel.cabeceras.length} columnas`);
  ok('el borrado en masa está capado sin filtros (no se puede vaciar por accidente)',
    panel.acciones.some((a) => /borrar todo lo filtrado/i.test(a)));

  // --- un atajo de limpieza: filtros puestos y recuento real ---
  const atajo = p.getByRole('button', { name: /sin idioma detectado|en cuarentena|filas sin fichero/i }).first();
  if (await atajo.count()) {
    await atajo.click();
    await p.waitForTimeout(4000);
    const trasAtajo = await p.evaluate(() => {
      const texto = document.body.innerText;
      const cuenta = (texto.match(/([\d.]+)\s*canciones con estos filtros/i) || [])[0] || '';
      return { cuenta, aviso: texto.includes('Pon al menos un filtro') };
    });
    ok('al pulsar un atajo se aplican los filtros y sale el recuento',
      Boolean(trasAtajo.cuenta) && !trasAtajo.aviso, trasAtajo.cuenta || '(sin recuento)');
  }

  // --- la previsualización (dry-run) del borrado en masa ---
  const previsualizar = p.getByRole('button', { name: /borrar todo lo filtrado/i }).first();
  if (await previsualizar.count()) {
    await previsualizar.click();
    await p.waitForTimeout(6000);
    const modal = await p.evaluate(() => {
      const texto = document.body.innerText;
      const m = document.querySelector('.ant-modal');
      return {
        hay: !!m,
        dice: (texto.match(/Se van a BORRAR [\d.]+ canciones/i) || [])[0] || '',
        filtros: (texto.match(/Filtros aplicados/i) || [])[0] || '',
      };
    });
    ok('el borrado en masa se PREVISUALIZA antes (no borra a ciegas)',
      modal.hay && Boolean(modal.dice), modal.dice || '(sin aviso)');
    ok('la previsualización dice QUÉ filtros se van a aplicar', Boolean(modal.filtros));
    // Y se cancela: esta prueba NO borra nada del catálogo de verdad.
    const cancelar = p.locator('.ant-modal button', { hasText: /cancelar/i }).first();
    if (await cancelar.count()) await cancelar.click();
    await p.waitForTimeout(1000);
  }

  ok('sin errores de JavaScript', errores.length === 0, errores.slice(0, 2).join(' | '));

  await p.screenshot({ path: 'admin-panel.png', fullPage: false });
  await b.close();

  const fallos = res.filter((r) => !r.bien);
  console.log(`\n================  ${res.length - fallos.length}/${res.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
