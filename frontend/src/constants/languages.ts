import type { Languages } from '../interfaces/languages';

/**
 * Idiomas de la interfaz.
 *
 * El español es castellano de España (tuteo, "añadir" en vez de "agregar", etc.). Antes
 * ponía «Español (Argentina)» y las traducciones tenían voseo («¿Qué querés reproducir?»).
 */
export const AVAILABLE_LANGUAGES = [
  { value: 'en', label: 'English', englishLabel: 'English' },
  {
    value: 'es',
    label: 'Español (España)',
    englishLabel: 'Spanish',
  },
] as {
  label: string;
  value: Languages;
  englishLabel: string;
}[];
