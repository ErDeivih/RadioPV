export const album = {
  songs: 'canciones',
  // Faltaba `song` (singular): la cabecera de un álbum de UNA canción decía «1 song» en inglés en
  // mitad de la interfaz en castellano, porque i18next no encontraba la clave y se iba al idioma de
  // reserva. La página de listas ya la tenía (`playlist.song`); aquí se había olvidado.
  song: 'canción',
  Album: 'Álbum',
  'More by': 'Más de',
};
