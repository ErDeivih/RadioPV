/**
 * Etiquetas legibles de los valores que usa el recolector (género, idioma, estado).
 *
 * POR QUÉ ESTÁ AQUÍ Y NO EN EL PANEL
 * ----------------------------------
 * Estaban dentro de `pages/Admin/api.ts`, y el panel era el único sitio que las usaba. Pero la
 * aplicación **también** enseña esos valores: la pantalla de explorar sacaba tarjetas que decían
 * «es», «en» o «techhouse» en crudo, y la cabecera de un género ponía lo mismo. Con las etiquetas en
 * un módulo compartido, las dos partes dicen lo mismo y no hay dos listas que se puedan separar (ya
 * pasó con la tabla de géneros del recolector).
 */

/** Etiquetas legibles para los idiomas que usa el recolector. */
export const LANGUAGE_LABELS: Record<string, string> = {
  es: 'Español',
  en: 'Inglés',
  it: 'Italiano',
  fr: 'Francés',
  pt: 'Portugués',
  other: 'Otro / sin detectar',
};

/** Etiquetas legibles para los géneros del catálogo. */
export const GENRE_LABELS: Record<string, string> = {
  reggaeton: 'Reggaetón',
  pop: 'Pop',
  rock: 'Rock',
  bachata: 'Bachata',
  salsa: 'Salsa',
  merengue: 'Merengue',
  latin: 'Latino / Urbano',
  dance: 'Dance / Electrónica',
  rap: 'Rap / Hip-Hop',
  ballad: 'Balada',
  cumbia: 'Cumbia',
  corridos: 'Corridos / Mexicano',
  flamenco: 'Flamenco',
  reggae: 'Reggae',
  disco: 'Disco / Funk',
  classical: 'Clásica',
  house: 'House',
  techhouse: 'Tech house / Guaracha',
  electro: 'Electrónica',
  instrumental: 'Instrumental',
  soundtrack: 'Banda sonora',
  jazz: 'Jazz',
  blues: 'Blues',
  metal: 'Metal',
  indie: 'Indie',
  folk: 'Folk',
  techno: 'Techno',
  lofibeat: 'Lo-Fi',
  gospel: 'Gospel',
  banda: 'Banda',
  soul: 'Soul / R&B',
  'r&b': 'R&B',
  other: 'Variado',
};

export const STATUS_LABELS: Record<string, string> = {
  pendiente: 'Pendiente',
  descargando: 'Descargando',
  descargada: 'Descargada',
  fallida: 'Fallida',
  en_cola: 'En cola',
  cuarentena: 'Cuarentena',
};

export const labelLang = (v?: string | null) => (v ? LANGUAGE_LABELS[v] ?? v : '—');
export const labelGenre = (v?: string | null) => (v ? GENRE_LABELS[v] ?? v : '—');
export const labelStatus = (v?: string | null) => (v ? STATUS_LABELS[v] ?? v : '—');

/**
 * Etiqueta de un facet de explorar (`genre:techhouse`, `language:es`, `era:00s`, `mood:fiesta`).
 * Se usa para el NOMBRE visible; el `value` que viaja en la URL sigue siendo el valor crudo.
 */
export const labelFacet = (tipo: string, valor: string): string => {
  if (tipo === 'genre') return GENRE_LABELS[valor] ?? valor;
  if (tipo === 'language') return LANGUAGE_LABELS[valor] ?? valor;
  if (tipo === 'era') return valor === 'vintage' ? 'Clásicos' : valor;
  return valor;
};
