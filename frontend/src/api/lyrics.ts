import axios from '../axios';

/** Letra de una canción. */
export interface Letra {
  letra: string | null;
  encontrada: boolean;
  fuente?: string;
  titulo_buscado?: string;
  artista_buscado?: string;
}

/**
 * Pide la letra de una canción.
 *
 * El servidor la busca fuera (lyrics.ovh) y la guarda en caché; si no la encuentra responde
 * `encontrada: false` sin error, porque no tener letra es lo normal en buena parte del catálogo
 * (música poco conocida, remixes, sesiones de DJ).
 */
export const getLyrics = async (trackId: string): Promise<Letra> => {
  const { data } = await axios.get<Letra>(`/tracks/${trackId}/lyrics`, { timeout: 20000 });
  return data;
};
