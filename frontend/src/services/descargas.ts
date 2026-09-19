import axios from '../axios';
import { API_BASE } from '../apiBase';

/**
 * Descargar música a una carpeta del dispositivo.
 *
 * PARA QUÉ
 * --------
 * Para cargar los auriculares rápido: eliges una lista, eliges una carpeta y los ficheros van
 * ahí con el nombre «Artista - Título.mp3», listos para copiarlos o para que los lea cualquier
 * reproductor. Sin pasar por la nube de nadie.
 *
 * CÓMO FUNCIONA EN CADA SITIO
 * ---------------------------
 * · **Chrome/Edge de escritorio**: `showDirectoryPicker()` deja elegir LA carpeta y escribir
 *   dentro, así que los ficheros van donde el usuario dice. Es lo ideal para pasar música a los
 *   auriculares o a una tarjeta.
 * · **Móvil (Android/iOS)**: los navegadores no dejan elegir carpeta, así que se descargan con el
 *   mecanismo normal del navegador (van a la carpeta de Descargas). Es lo que se puede hacer sin
 *   una app nativa; se avisa en pantalla para que no parezca que no ha funcionado.
 * · **Firefox de escritorio**: tampoco tiene `showDirectoryPicker`, así que usa el mismo camino.
 */

/** ¿Se puede elegir carpeta? */
export const puedeElegirCarpeta = (): boolean =>
  typeof (window as unknown as { showDirectoryPicker?: unknown }).showDirectoryPicker === 'function';

interface ManejadorCarpeta {
  getFileHandle: (nombre: string, opciones?: { create?: boolean }) => Promise<{
    createWritable: () => Promise<{ write: (datos: Blob) => Promise<void>; close: () => Promise<void> }>;
  }>;
}

/** Pide al usuario una carpeta. Devuelve null si cancela. */
export const elegirCarpeta = async (): Promise<ManejadorCarpeta | null> => {
  const picker = (window as unknown as {
    showDirectoryPicker?: (o?: { mode?: string }) => Promise<ManejadorCarpeta>;
  }).showDirectoryPicker;
  if (!picker) return null;
  try {
    return await picker({ mode: 'readwrite' });
  } catch {
    return null;   // el usuario ha cancelado: no es un error
  }
};

/** Nombre de fichero seguro para cualquier sistema («Artista - Título.mp3»). */
export const nombreDeFichero = (artista: string, titulo: string): string => {
  const limpio = `${artista} - ${titulo}`
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 120);
  return `${limpio || 'cancion'}.mp3`;
};

/** Trae el audio de una canción como blob (usa el mismo token de streaming que el reproductor). */
const traerAudio = async (trackId: string, streamToken: string): Promise<Blob> => {
  const r = await fetch(
    `${API_BASE}/stream/${trackId}?t=${encodeURIComponent(streamToken)}`,
    { credentials: 'include' }
  );
  if (!r.ok) throw new Error(`no se pudo descargar (HTTP ${r.status})`);
  return await r.blob();
};

const tokenDeStreaming = async (): Promise<string> => {
  const { data } = await axios.post<{ token: string }>('/auth/stream-token');
  return data.token;
};

export interface Progreso {
  hechas: number;
  total: number;
  actual: string;
  fallos: number;
}

/**
 * Descarga una lista de canciones a la carpeta elegida (o al sistema, si no se puede elegir).
 *
 * `onProgreso` se llama en cada canción, para poder enseñar por dónde va: descargar 50 canciones
 * tarda, y sin saber qué pasa la gente cree que se ha colgado.
 */
export const descargarCanciones = async (
  canciones: { id: string; artista: string; titulo: string }[],
  carpeta: ManejadorCarpeta | null,
  onProgreso?: (p: Progreso) => void
): Promise<Progreso> => {
  const token = await tokenDeStreaming();
  const progreso: Progreso = { hechas: 0, total: canciones.length, actual: '', fallos: 0 };

  for (const c of canciones) {
    progreso.actual = `${c.artista} - ${c.titulo}`;
    onProgreso?.({ ...progreso });
    try {
      const blob = await traerAudio(c.id, token);
      const nombre = nombreDeFichero(c.artista, c.titulo);
      if (carpeta) {
        const fichero = await carpeta.getFileHandle(nombre, { create: true });
        const escritor = await fichero.createWritable();
        await escritor.write(blob);
        await escritor.close();
      } else {
        // Sin elección de carpeta: descarga normal del navegador.
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = nombre;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // Se espera un poco entre descargas: si se piden 30 de golpe, el navegador las bloquea.
        await new Promise((listo) => setTimeout(listo, 400));
      }
      progreso.hechas += 1;
    } catch {
      progreso.fallos += 1;
    }
    onProgreso?.({ ...progreso });
  }
  return progreso;
};
