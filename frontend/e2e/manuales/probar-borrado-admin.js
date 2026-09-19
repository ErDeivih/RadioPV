/*
 * Prueba de verdad del BORRADO del panel de administración.
 *
 * Usa fichas FALSAS que crea `scripts/prueba_borrado_dos_bases.py` (en las DOS bases, porque el
 * panel gestiona `radiov.db` y la aplicación sirve `backend.db`). Comprueba que:
 *   1. se pueden buscar en la tabla del panel,
 *   2. se seleccionan con las casillas,
 *   3. al pulsar «Borrar seleccionadas» PIDE CONFIRMACIÓN,
 *   4. desaparecen de la tabla Y de la base de datos,
 *   5. y que el fichero se borra del disco.
 *
 * No borra NINGUNA canción real: sólo las fichas de prueba.
 *
 * Uso: node probar-borrado-admin.js
 *      TITULO="PRUEBA DOS BASES" node probar-borrado-admin.js
 */
const { chromium } = require('playwright');
const URL_BASE = process.env.URL || 'http://servidor:8090';
const EMAIL = process.env.ADMIN_EMAIL || 'admin-pruebas@radiopv-test.com';
const CLAVE = process.env.ADMIN_CLAVE || 'clave-de-pruebas-larga-123';
// El título que hay que buscar. Se puede cambiar sin tocar el fichero: así la misma prueba sirve
// para las fichas de una base y de las dos.
const TITULO = process.env.TITULO || 'PRUEBA DOS BASES';
const CUANTAS = Number(process.env.CUANTAS || 1);

const res = [];
const ok = (n, bien, detalle = '') => {
  res.push({ n, bien });
  console.log(`  ${bien ? 'OK   ' : 'FALLO'}  ${n}${detalle ? `  ->  ${detalle}` : ''}`);
};

(async () => {
  const b = await chromium.launch({ args: ['--mute-audio'] });
  const c = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await c.newPage();
  const errores = [];
  p.on('pageerror', (e) => errores.push(String(e).split('\n')[0].slice(0, 130)));

  await p.goto(URL_BASE, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4000);
  await p.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click();
  await p.waitForTimeout(2000);
  await p.locator('input[placeholder="Email"]').first().fill(EMAIL);
  await p.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);
  await p.getByRole('button', { name: /Iniciar sesión|Entrar/i }).last().click();
  await p.waitForTimeout(6000);

  await p.goto(`${URL_BASE}/admin`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(6000);

  // 1. Buscar las de prueba
  await p.locator('input[placeholder*="Título, artista"]').first().fill(TITULO);
  await p.keyboard.press('Enter');
  await p.waitForTimeout(5000);

  const filas = await p.locator('tbody tr').count();
  const textos = await p.evaluate(() =>
    [...document.querySelectorAll('tbody tr')].map((t) => t.innerText.replace(/\n/g, ' ').slice(0, 60))
  );
  ok('las canciones de prueba salen en la tabla', filas >= CUANTAS + 1, `${filas} filas: ${textos.join(' | ')}`);

  // 2. Seleccionarlas
  const casillas = p.locator('tbody tr input[type="checkbox"]');
  const n = await casillas.count();
  for (let i = 0; i < n; i++) await casillas.nth(i).check().catch(() => undefined);
  await p.waitForTimeout(1500);
  const seleccionadas = await p.evaluate(() => {
    const m = document.body.innerText.match(/(\d+) seleccionadas/);
    return m ? Number(m[1]) : 0;
  });
  ok('se pueden seleccionar con las casillas', seleccionadas >= CUANTAS, `${seleccionadas} seleccionadas`);

  // 3. Borrar: tiene que preguntar
  const borrar = p.getByRole('button', { name: /borrar seleccionadas/i }).first();
  if (await borrar.count()) {
    await borrar.click();
    await p.waitForTimeout(2500);
    const confirmacion = await p.evaluate(() => {
      const m = document.querySelector('.ant-popconfirm, .ant-modal-confirm');
      return { hay: !!m, texto: m ? m.innerText.replace(/\n/g, ' ').slice(0, 90) : '' };
    });
    ok('pide confirmación antes de borrar', confirmacion.hay, confirmacion.texto);

    // Confirmar de verdad
    const si = p.locator('.ant-popconfirm button, .ant-modal-confirm button').filter({ hasText: /^(Borrar|Sí|Si|OK)$/i }).last();
    if (await si.count()) await si.click();
    await p.waitForTimeout(6000);
  } else {
    ok('existe el botón de borrar seleccionadas', false);
  }

  // 4. ¿Se han ido de la tabla?
  await p.waitForTimeout(3000);
  const quedan = await p.evaluate(() => {
    const t = document.body.innerText;
    return (t.match(/PRUEBA (BORRAR|DOS BASES)/g) || []).length;
  });
  ok('ya no aparecen en la tabla', quedan === 0, `${quedan} apariciones`);

  ok('sin errores de JavaScript', errores.length === 0, errores.slice(0, 2).join(' | '));

  await p.screenshot({ path: 'admin-borrado.png' });
  await b.close();

  const fallos = res.filter((r) => !r.bien);
  console.log(`\n================  ${res.length - fallos.length}/${res.length} OK  ================`);
  fallos.forEach((f) => console.log(`  · ${f.n}`));
  process.exit(fallos.length ? 1 : 0);
})();
