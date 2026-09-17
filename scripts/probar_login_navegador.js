/**
 * Prueba de verdad, en un navegador real, de los TRES botones de "Iniciar sesión".
 *
 * Es la comprobacion que faltaba: la API puede responder perfectamente por curl y aun asi
 * la interfaz no hacer nada. Aqui se pulsa, se rellena y se comprueba el resultado.
 *
 *   node probar-login.js http://192.168.1.139:8090
 */
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://192.168.1.139:8090';
const EMAIL = `navegador-${Date.now()}@radiopv-test.com`;
const CLAVE = 'clave-de-pruebas-larga-123';

const resultados = [];
function check(nombre, ok, detalle = '') {
  resultados.push({ nombre, ok });
  console.log(`  [${ok ? 'OK ' : 'FALLO'}] ${nombre}${detalle ? '  ·  ' + detalle : ''}`);
}

/** Espera a que aparezca el modal de acceso (el campo de email). */
async function modalAbierto(page, ms = 8000) {
  try {
    await page.locator('input[placeholder="Email"]').first().waitFor({ timeout: ms, state: 'visible' });
    return true;
  } catch {
    return false;
  }
}

(async () => {
  const navegador = await chromium.launch();
  const contexto = await navegador.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await contexto.newPage();

  const api = [];
  const fallos = [];
  const erroresJs = [];
  page.on('response', (r) => {
    if (r.url().includes('/api/')) api.push(`${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`);
  });
  page.on('requestfailed', (r) => fallos.push(`${r.url()} -> ${r.failure()?.errorText}`));
  page.on('pageerror', (e) => erroresJs.push(String(e)));

  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(5000);

  // ---------------------------------------------------------------- 1. los tres botones
  console.log('\n=== 1. los tres botones de "Iniciar sesión" abren el acceso? ===');
  const cuantos = await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).count();
  check('hay tres botones en la portada', cuantos === 3, `${cuantos} encontrados`);

  for (let i = 0; i < cuantos; i++) {
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4000);

    // El modal abierto tapa toda la pantalla: si no se cierra, el siguiente clic lo
    // intercepta el overlay y el fallo parece del boton cuando es del guion de prueba.
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(800);

    const yaAbierto = await modalAbierto(page, 1200);
    if (yaAbierto) console.log('      (aviso: el modal ya estaba abierto antes de pulsar)');

    const antes = api.length;
    const boton = page.getByRole('button', { name: 'Iniciar sesión', exact: true }).nth(i);
    const texto = (await boton.innerText().catch(() => '?')).trim();

    let clickOk = true;
    try {
      await boton.click({ timeout: 10000 });
    } catch (e) {
      clickOk = false;
      console.log(`      (el clic fallo: ${String(e.message).split('\n')[0]})`);
    }
    await page.waitForTimeout(2500);

    const abierto = await modalAbierto(page, 6000);
    const llamadas = api.slice(antes);
    check(`boton ${i + 1} ("${texto}") abre el modal`, abierto,
          llamadas.length ? `llamadas: ${llamadas.join(', ')}` : 'sin llamadas a la API');
    if (!clickOk) check(`boton ${i + 1}: el clic no fue interceptado`, false);
  }

  // ---------------------------------------------------------------- 2. registro real
  console.log('\n=== 2. registro completo desde el modal ===');
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(800);
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).first().click({ timeout: 15000 });
  const abierto = await modalAbierto(page, 12000);
  check('el modal se abre', abierto);
  if (!abierto) {
    console.log('\n  No se puede seguir sin modal.');
    await navegador.close();
    process.exit(1);
  }

  const pestanaRegistro = page.getByRole('button', { name: 'Registrarse', exact: true });
  check('existe la pestaña "Registrarse"', await pestanaRegistro.count() > 0);
  await pestanaRegistro.first().click();
  await page.waitForTimeout(800);

  const campoNombre = page.locator('input[placeholder="Nombre"]');
  check('al pulsar "Registrarse" aparece el campo Nombre',
        await campoNombre.count() > 0 && await campoNombre.first().isVisible());

  await campoNombre.first().fill('Prueba Navegador');
  await page.locator('input[placeholder="Email"]').first().fill(EMAIL);
  await page.locator('input[placeholder="Contraseña"]').first().fill(CLAVE);

  const antesRegistro = api.length;
  await page.getByRole('button', { name: 'Crear cuenta', exact: true }).first().click();
  await page.waitForTimeout(6000);

  const llamadasRegistro = api.slice(antesRegistro);
  console.log(`      llamadas durante el registro: ${llamadasRegistro.join(' | ') || '(ninguna)'}`);
  check('el boton "Crear cuenta" llama a la API',
        llamadasRegistro.some((l) => l.includes('/api/auth/register')),
        llamadasRegistro.join(', ') || 'ninguna llamada');
  check('la API acepta el registro (200)',
        llamadasRegistro.some((l) => l.startsWith('200') && l.includes('register')));

  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  check('la sesion queda guardada en el navegador', !!token,
        token ? `${token.slice(0, 20)}...` : 'sin token');

  await page.waitForTimeout(3000);
  const texto = await page.evaluate(() => document.body.innerText.slice(0, 300));
  const yaDentro = !/inicia sesión para acceder/i.test(texto);
  check('la interfaz cambia a "dentro" (ya no pide acceso)', yaDentro);
  console.log(`      texto de la pantalla: ${JSON.stringify(texto.slice(0, 160))}`);

  await page.screenshot({ path: 'tras-login.png' });

  // ---------------------------------------------------------------- 3. salud general
  console.log('\n=== 3. salud de la sesion en el navegador ===');
  check('sin errores de JavaScript', erroresJs.length === 0, erroresJs.slice(0, 2).join(' | '));
  check('sin peticiones fallidas', fallos.length === 0, fallos.slice(0, 2).join(' | '));
  const malas = api.filter((l) => /^(4|5)\d\d/.test(l));
  check('ninguna llamada a la API devolvio error', malas.length === 0, malas.slice(0, 4).join(' | '));

  console.log('\n      todas las llamadas a la API:');
  [...new Set(api)].forEach((l) => console.log(`        ${l}`));

  await navegador.close();

  const fallosTot = resultados.filter((r) => !r.ok);
  console.log(`\n  ===== ${resultados.length - fallosTot.length}/${resultados.length} comprobaciones OK =====`);
  console.log(`\n  usuario de prueba creado: ${EMAIL}`);
  console.log('  !!! OJO: al ser el primero, ese usuario es ADMIN.');
  console.log('  !!! Borralo antes de que te registres tu, o entrarias sin permisos:');
  console.log('  !!!   python3 /tmp/limpiar-usuarios-prueba.py');
  if (fallosTot.length) {
    console.log('\n  fallos:');
    fallosTot.forEach((f) => console.log(`    - ${f.nombre}`));
    process.exit(1);
  }
})();
