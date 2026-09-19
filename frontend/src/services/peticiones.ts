import axios from '../axios';

/** Una canción pedida desde la app, con su estado. */
export interface Peticion {
  id: number;
  text: string;
  status: 'pendiente' | 'descargada' | 'fallida' | string;
  created_at: string | null;
}

/**
 * Pide una canción para que se descargue en la biblioteca.
 *
 * El recolector (que ahora corre en el PC) recoge las peticiones pendientes, las busca en las
 * tiendas de música y, si no están, **directamente en YouTube** —que es donde están los mashups,
 * los remixes y las sesiones de DJ— y contesta si la ha encontrado o no.
 */
export const crearPeticion = async (text: string) => {
  const { data } = await axios.post<{ ok: boolean; text: string; repetida?: boolean }>(
    '/requests',
    { text }
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

/** ¿Está ya en la biblioteca? Se usa mientras se escribe, para no pedir lo que ya hay. */
export const yaEstaEnLaBiblioteca = async (q: string) => {
  if (!q.trim()) return [];
  const { data } = await axios.get<{ id: number; title: string; artist: string }[]>('/tracks', {
    params: { q: q.trim(), limit: 5 },
  });
  return data;
};
