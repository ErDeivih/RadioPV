/**
 * Verifica en un navegador REAL que la interfaz esta en castellano de Espana.
 *
 * Comprueba tres cosas:
 *   1. que no quede ninguna marca argentina a la vista (voseo y vocabulario)
 *   2. que el modal de idiomas este traducido y diga "Espanol (Espana)"
 *   3. que se pueda cambiar de idioma y que al volver siga en castellano
 *
 *   node probar-idioma.js http://192.168.1.139:8090
 */
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://192.168.1.139:8090';

// Marcas de espanol rioplatense que NO deben aparecer en la interfaz.
const MARCAS_ARGENTINAS = [
  'querés', 'queres reproducir', 'Probá', 'proba buscar', 'Seguí',
  'Agregar', 'agregado', 'agregarlo', 'Grilla', 'gustadas',
  'iniciaste', 'Dejaste de seguir', 'Empezaste a seguir',
  'Collapsar', 'Contactame', 'Compilaciones', 'Argentina',
  'tenés', 'podés', 'elegí',
];

// Expresiones que SI deben aparecer (castellano de Espana).
const ESPERADAS = [
  'quieres reproducir', 'añad', 'Cuadrícula', 'Contraer', 'Contáctame',
  'Recopilatorios', 'España',
];

const resultados = [];
function check(nombre, ok, detalle = '') {
  resultados.push({ nombre, ok });
  console.log(`  [${ok ? 'OK ' : 'FALLO'}] ${nombre}${detalle ? '  ·  ' + detalle : ''}`);
}

(async () => {
  const navegador = await chromium.launch();
  const contexto = await navegador.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await contexto.newPage();

  const errores = [];
  page.on('pageerror', (e) => errores.push(String(e)));

  console.log(`\n=== abriendo ${BASE} ===`);
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(6000);

  // ---------------------------------------------------------------- 1. texto visible
  const texto = await page.evaluate(() => document.body.innerText);
  const plano = texto.toLowerCase();

  console.log('\n=== 1. marcas argentinas en la interfaz ===');
  const encontradas = MARCAS_ARGENTINAS.filter((m) => plano.includes(m.toLowerCase()));
  check('no queda ninguna marca argentina a la vista', encontradas.length === 0,
        encontradas.length ? `encontradas: ${encontradas.join(', ')}` : 'ninguna');

  console.log('\n=== 2. expresiones de castellano de España ===');
  const faltan = ESPERADAS.filter((e) => !plano.includes(e.toLowerCase()));
  // No todas tienen por que estar en la portada: se informa, pero solo falla si no hay
  // NINGUNA, que indicaria que la app no esta en castellano.
  const hay = ESPERADAS.length - faltan.length;
  check('la interfaz usa castellano de España', hay >= 1,
        `presentes: ${ESPERADAS.filter((e) => plano.includes(e.toLowerCase())).join(', ') || 'ninguna'}`);
  if (faltan.length) console.log(`        (no estan en esta pantalla: ${faltan.join(', ')})`);

  console.log('\n=== 3. el modal de idiomas ===');
  const botonIdioma = page.locator('.language-button').first();
  if (await botonIdioma.count() === 0) {
    check('existe el boton de idioma', false, 'no encontrado');
  } else {
    const etiquetaBoton = (await botonIdioma.innerText()).trim();
    console.log(`        el boton dice: "${etiquetaBoton}"`);
    check('el boton ya no dice "Argentina"', !/argentina/i.test(etiquetaBoton), etiquetaBoton);
    check('el boton dice "Español (España)"', /españa/i.test(etiquetaBoton), etiquetaBoton);

    await botonIdioma.click();
    await page.waitForTimeout(2000);
    const modal = page.locator('.language-modal');
    const textoModal = (await modal.innerText().catch(() => '')).trim();
    console.log(`        el modal dice: ${JSON.stringify(textoModal.slice(0, 120))}`);

    check('el titulo del modal esta traducido (no "Choose a language")',
          !/choose a language/i.test(textoModal), textoModal.slice(0, 60));
    check('el titulo dice "Elige un idioma"', /elige un idioma/i.test(textoModal));
    check('la opcion de español dice "Español (España)"', /español \(españa\)/i.test(textoModal));

    // Probar a cambiar a ingles y volver
    const botonIngles = page.locator('.language-grid button', { hasText: 'English' }).first();
    if (await botonIngles.count() > 0) {
      await botonIngles.click();
      await page.waitForTimeout(3000);
      const textoEn = await page.evaluate(() => document.body.innerText);
      check('cambiar a ingles funciona', /log in|your library|search/i.test(textoEn),
            JSON.stringify(textoEn.slice(0, 70)));

      // Volver a español
      const boton2 = page.locator('.language-button').first();
      await boton2.click();
      await page.waitForTimeout(1500);
      const esp = page.locator('.language-grid button', { hasText: 'Español' }).first();
      await esp.click();
      await page.waitForTimeout(3000);
      const textoEs = await page.evaluate(() => document.body.innerText);
      const planoEs = textoEs.toLowerCase();
      check('volver a español funciona',
            /iniciar sesión|tu biblioteca|buscar/i.test(textoEs),
            JSON.stringify(textoEs.slice(0, 70)));
      const reincidentes = MARCAS_ARGENTINAS.filter((m) => planoEs.includes(m.toLowerCase()));
      check('al volver sigue sin marcas argentinas', reincidentes.length === 0,
            reincidentes.join(', ') || 'ninguna');
    }
  }

  console.log('\n=== 4. salud ===');
  check('sin errores de JavaScript', errores.length === 0, errores.slice(0, 2).join(' | '));

  await page.screenshot({ path: 'idioma.png' });
  await navegador.close();

  const fallos = resultados.filter((r) => !r.ok);
  console.log(`\n  ===== ${resultados.length - fallos.length}/${resultados.length} comprobaciones OK =====`);
  if (fallos.length) {
    console.log('  fallos:');
    fallos.forEach((f) => console.log(`    - ${f.nombre}`));
    process.exit(1);
  }
})();
