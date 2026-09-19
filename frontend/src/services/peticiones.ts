import axios from '../axios';

/** Una canción pedida desde la app, con su estado. */
export interface Peticion {
  id: number;
  text: string;
  status: 'pendiente' | 'descargada' | 'fallida' | string;
  created_at: string | null;
}

/** Un resultado de YouTube: la versión concreta que se puede pedir. */
export interface ResultadoYoutube {
  video_id: string;
  titulo: string;
  canal: string;
  duracion: number | null;
  en_catalogo: boolean;
}

/** Lo que ya está en la biblioteca (para poder oírlo en vez de pedirlo). */
export interface EnBiblioteca {
  id: number;
  titulo: string;
  artista: string;
  duracion: number | null;
}

/** Lo que devuelve la búsqueda de la página de pedir canciones. */
export interface BusquedaParaPedir {
  consulta: string;
  aviso: string | null;
  en_biblioteca: EnBiblioteca[];
  en_youtube: ResultadoYoutube[];
  en_cola: { id: number; text: string }[];
}

/**
 * Pide una canción para que se descargue en la biblioteca.
 *
 * `youtubeId` es el vídeo EXACTO que el usuario ha elegido en la lista de resultados. Es la
 * diferencia entre bajar «lo que el buscador crea que es» y bajar la versión que se ha pedido: de
 * un mismo tema hay el original, el remix, el directo y veinte subidas distintas.
 */
export const crearPeticion = async (text: string, youtubeId?: string, duration?: number | null) => {
  const { data } = await axios.post<{ ok: boolean; text: string; repetida?: boolean }>(
    '/requests',
    { text, youtube_id: youtubeId, duration }
  );
  return data;
};

/** Mis peticiones, de la más reciente a la más antigua. */
export const misPeticiones = async () => {
  const { data } = await axios.get<Peticion[]>('/requests');
  return data;
};

/** Quita una petición de mi lista. */
export const borrarPeticion = async (id: number) => {
  await axios.delete(`/requests/${id}`);
};

/**
 * Busca una canción para pedirla: primero en casa, y si no está, en YouTube.
 *
 * Esto es lo que convierte la página en algo útil: antes era una caja de texto a ciegas —no sabías
 * si ya la tenías ni cuál de las versiones se iba a bajar— y ahora se ve lo que hay antes de pedir.
 */
export const buscarParaPedir = async (q: string) => {
  const { data } = await axios.get<BusquedaParaPedir>('/requests/buscar', {
    params: { q: q.trim() },
    timeout: 25000, // YouTube tarda: mejor esperar que dejar la página a medias
  });
  return data;
};

/** ¿Está ya en la biblioteca? Se usa mientras se escribe, para no pedir lo que ya hay. */
export const yaEstaEnLaBiblioteca = async (q: string) => {
  if (!q.trim()) return [];
  const { data } = await axios.get<{ id: number; title: string; artist: string }[]>('/tracks', {
    params: { q: q.trim(), limit: 5 },
  });
  return data;
};

/** «3:45» a partir de segundos. Devuelve null si no se sabe. */
export const duracionLegible = (segundos?: number | null): string | null => {
  if (!segundos || segundos <= 0) return null;
  const total = Math.round(segundos);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`;
};
