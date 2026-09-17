import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import * as en from './en';
import * as es from './es';

i18n
  .use(initReactI18next) // passes i18n down to react-i18next
  .init({
    // the translations
    // (tip move them in a JSON file and import them,
    // or even better, manage them via a UI: https://react.i18next.com/guides/multiple-translation-files#manage-your-translations-with-a-management-gui)
    resources: {
      en,
      es,
    },
    // La aplicación es en español de España: arranca en español y no en inglés. Con `lng: 'en'`
    // la primera pintada salía en inglés hasta que el componente de arriba llamaba a
    // `changeLanguage` (parpadeo de idioma en cada carga). El inglés se mantiene como respaldo
    // para las claves que aún no estén traducidas.
    lng: 'es',
    fallbackLng: 'es',

    interpolation: {
      escapeValue: false, // react already safes from xss => https://www.i18next.com/translation-function/interpolation#unescape
    },
  });
