/**
 * Compara las claves de traduccion entre ingles y espanol y busca texto SIN traducir.
 *
 *   node scripts/auditar_traducciones.js
 *
 * Hace tres comprobaciones:
 *   1. claves que estan en un idioma y faltan en el otro
 *   2. traducciones que son identicas al ingles (sospechosas de no haberse traducido)
 *   3. texto de interfaz escrito a pelo en los componentes (sin pasar por t())
 */
const fs = require('fs');
const path = require('path');

const RAIZ = path.resolve(__dirname, '..');
const I18N = path.join(RAIZ, 'src', 'i18n');

/** Saca los pares clave/valor de un fichero de traduccion, que es un objeto literal simple. */
function leerIdioma(idioma) {
  const dir = path.join(I18N, idioma);
  const todo = {};
  for (const f of fs.readdirSync(dir).filter((n) => n.endsWith('.ts') && n !== 'index.ts')) {
    const src = fs.readFileSync(path.join(dir, f), 'utf8');
    // Claves entre comillas simples, dobles o backticks, con su valor.
    const re = /^\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`((?:[^`\\]|\\.)*)`)\s*:\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`((?:[^`\\]|\\.)*)`)\s*,?\s*$/gm;
    let m;
    while ((m = re.exec(src)) !== null) {
      const clave = m[1] ?? m[2] ?? m[3];
      const valor = m[4] ?? m[5] ?? m[6];
      todo[clave] = { valor, fichero: f };
    }
  }
  return todo;
}

const en = leerIdioma('en');
const es = leerIdioma('es');

console.log('='.repeat(72));
console.log(`  INGLES: ${Object.keys(en).length} claves   |   ESPANOL: ${Object.keys(es).length} claves`);
console.log('='.repeat(72));

const faltanEnEs = Object.keys(en).filter((k) => !(k in es));
const faltanEnEn = Object.keys(es).filter((k) => !(k in en));

console.log(`\n--- 1. claves en INGLES que faltan en ESPANOL (${faltanEnEs.length}) ---`);
faltanEnEs.forEach((k) => console.log(`  ${k}   [${en[k].fichero}]  ->  "${en[k].valor}"`));

console.log(`\n--- claves en ESPANOL que no estan en INGLES (${faltanEnEn.length}) ---`);
faltanEnEn.forEach((k) => console.log(`  ${k}   [${es[k].fichero}]`));

console.log('\n--- 2. traducciones identicas al ingles (sin traducir?) ---');
const iguales = Object.keys(es).filter((k) => en[k] && es[k].valor === en[k].valor);
iguales.forEach((k) => console.log(`  "${k}" = "${es[k].valor}"  [${es[k].fichero}]`));
if (!iguales.length) console.log('  (ninguna)');

// --- 3. texto a pelo en los componentes ---
console.log('\n--- 3. texto de interfaz SIN traducir en los componentes ---');
const componentes = [];
function recorrer(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) recorrer(p);
    else if (/\.tsx?$/.test(e.name)) componentes.push(p);
  }
}
recorrer(path.join(RAIZ, 'src'));

// Busca texto visible que no venga de t(...): entre > y <, o en title/placeholder/label
const patrones = [
  />\s*([A-Z][A-Za-z][A-Za-z ,'!?.-]{3,60})\s*</g,
  /(?:title|placeholder|label|description|okText|cancelText)\s*=\s*'([A-Z][A-Za-z][A-Za-z ,'!?.-]{3,60})'/g,
  /(?:title|placeholder|label|description)\s*=\s*"([A-Z][A-Za-z][A-Za-z ,'!?.-]{3,60})"/g,
];
const sospechosos = new Map();
for (const f of componentes) {
  const src = fs.readFileSync(f, 'utf8');
  for (const re of patrones) {
    let m;
    while ((m = re.exec(src)) !== null) {
      const texto = m[1].trim();
      // Descartar lo que claramente no es texto de interfaz
      if (/^(import|export|const|return|div|span|React|className|style|data-|aria-)/.test(texto)) continue;
      if (/^[A-Z_]+$/.test(texto)) continue;
      const rel = path.relative(RAIZ, f);
      if (!sospechosos.has(texto)) sospechosos.set(texto, new Set());
      sospechosos.get(texto).add(rel);
    }
  }
}
[...sospechosos.entries()]
  .sort((a, b) => b[1].size - a[1].size)
  .slice(0, 40)
  .forEach(([texto, ficheros]) => {
    console.log(`  "${texto}"`);
    [...ficheros].slice(0, 3).forEach((f) => console.log(`      ${f}`));
  });
console.log(`\n  total de textos sospechosos: ${sospechosos.size}`);
