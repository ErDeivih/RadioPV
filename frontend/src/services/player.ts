import axios from '../axios';
import type { Pagination } from '../interfaces/api';
import { Device } from '../interfaces/devices';
import type { PlayHistoryObject } from '../interfaces/player';
import { playerController } from '../player/playerController';
import { colaController } from '../player/queueController';
import { toTrack } from '../api/adapt';
import type { TrackOut } from '../api/types';
import type { Track } from '../interfaces/track';

// The device playback commands should target — the Web Playback SDK device by default, or
// whatever device the user explicitly transfers to. Sending `device_id` on `play` means we
// don't depend on Spotify already having an "active device", which avoids the 404
// "Device not found" (its message for "no active device" too). Persist to localStorage so the
// id survives dev-server hot-reloads, where the SDK's `ready` event won't fire again.
const DEVICE_STORAGE_KEY = 'playback_device_id';
let playbackDeviceId: string | null = null;
// Name of our Web Playback SDK device, used to re-resolve its id from the live devices list.
// The SDK assigns a NEW device_id on every (re)connect, so a cached id goes stale — matching
// by name is the reliable way to find the current device.
let playbackDeviceName: string | null = null;

export const setPlaybackDevice = (deviceId: string | null) => {
  playbackDeviceId = deviceId;
  try {
    if (deviceId) localStorage.setItem(DEVICE_STORAGE_KEY, deviceId);
  } catch {
    /* ignore storage errors */
  }
};

export const setPlaybackDeviceName = (name: string | null) => {
  playbackDeviceName = name;
};

const currentDeviceId = () => {
  if (playbackDeviceId) return playbackDeviceId;
  try {
    return localStorage.getItem(DEVICE_STORAGE_KEY);
  } catch {
    return null;
  }
};

const deviceParams = () => {
  const id = currentDeviceId();
  return id ? { device_id: id } : undefined;
};

// Resolve the current, live id of our SDK device from `/me/player/devices`, matching by name
// (falling back to the cached id). Updates the cache so subsequent calls hit the fast path.
const resolveLiveDeviceId = async (): Promise<string | null> => {
  try {
    const { data } = await axios.get<{ devices: Device[] }>('/me/player/devices');
    const match =
      (playbackDeviceName && data.devices.find((d) => d.name === playbackDeviceName)) ||
      data.devices.find((d) => d.id === currentDeviceId());
    if (match?.id) {
      setPlaybackDevice(match.id);
      return match.id;
    }
  } catch {
    /* ignore — fall back to the cached id below */
  }
  return currentDeviceId();
};

/**
 * @description Get information about the user’s current playback state, including track or episode, progress, and active device.
 */
const fetchPlaybackState = async () => {
  const response = await axios.get('/me/player');
  return response.data;
};

/**
 *
 * @description Transfer playback to a new device and optionally begin playback. This API only works for users who have Spotify Premium. The order of execution is not guaranteed when you use this API with other Player API endpoints.
 * @param deviceId The ID of the device this command is targeting. If not supplied, the user’s currently active device is the target.
 */
const transferPlayback = async (deviceId: string) => {
  // Remember the target before the request: even if this transfer 404s due to the
  // registration race, subsequent `startPlayback` calls carry `device_id` and recover.
  setPlaybackDevice(deviceId);
  await axios.put('/me/player', { device_ids: [deviceId] });
};

/**
 * @description Get information about a user’s available Spotify Connect devices. Some device models are not supported and will not be listed in the API response.
 */
const getAvailableDevices = async () => {
  // RadioPV: no hay "dispositivos" de Spotify Connect (D5 los quitó de la UI). El endpoint
  // /me/player/devices no existe en nuestra API; devolvemos vacío en vez de un 404 que se
  // disparaba en cada montaje del Layout.
  return { devices: [] as Device[] };
};

/**
 * @description Start a new context or resume current playback on the user's active device. This API only works for users who have Spotify Premium. The order of execution is not guaranteed when you use this API with other Player API endpoints.
 */
const tidDeUri = (uri: string) => {
  const p = String(uri).split(':');
  return p[p.length - 1];
};

// Cache por id para no re-pedir los tracks al re-encolar o reiniciar una lista.
const cacheTracks = new Map<string, TrackOut>();

const getTrackProf = async (id: string): Promise<Track | null> => {
  try {
    let out = cacheTracks.get(id);
    if (!out) {
      const { data } = await axios.get<TrackOut>(`/tracks/${id}`);
      out = data;
      cacheTracks.set(id, data);
    }
    return toTrack(out);
  } catch {
    return null;
  }
};

/** Resuelve una lista de `radiopv:track:{id}` a Tracks (en paralelo; las que fallen se omiten). */
const resolvLista = async (uris: string[]): Promise<Track[]> => {
  const res = await Promise.all(uris.map((u) => getTrackProf(tidDeUri(u))));
  return res.filter((x): x is Track => x !== null);
};

/**
 * @description Start a new context or resume current playback on the user's active device. This API only works for users who have Spotify Premium. The order of execution is not guaranteed when you use this API with other Player API endpoints.
 */
const startPlayback = async (
  body: { context_uri?: string; uris?: string[]; offset?: { position: number } } = {}
) => {
  // RadioPV: la reproducción va por nuestro <audio> (playerController), no por Spotify Connect.
  // Resolvemos el track y lo reproducimos; los uris son `radiopv:track:{id}`.
  const uris = body.uris || [];
  const trackUri = uris[0] || body.context_uri;
  if (!trackUri) {
    playerController.resume();
    return;
  }
  const parts = String(trackUri).split(':');
  const kind = parts[1];  // 'track' | 'album' | 'playlist' | ...
  // Para `track` es el id; para playlist, el id; para álbum, la clave `artista::álbum`.
  // Se usa todo lo que va DESPUÉS del tipo (y no el último trozo): la clave de un álbum lleva
  // `::` dentro, así que `parts[parts.length - 1]` se quedaba sólo con el nombre del álbum y la
  // URI reconstruida no coincidía con la de la página (el botón nunca marcaba "sonando").
  const id = parts.slice(2).join(':');
  // Posición de arranque dentro de la lista. Las tablas de canciones ya la mandaban
  // (`offset: { position: index }`), pero aquí se ignoraba y siempre sonaba la primera:
  // pulsar la quinta canción de una playlist reproducía la primera.
  // OJO: no se puede acotar aquí con `uris.length`, porque al abrir una playlist o un álbum la
  // llamada trae sólo `context_uri` y `uris` viene vacío (acotar contra 0 dejaba el offset en 0
  // y volvía a sonar siempre la primera). Se acota en cada rama, cuando ya se conoce la lista.
  const offset = Math.max(0, body.offset?.position ?? 0);

  if (kind === 'user' && parts[parts.length - 1] === 'collection') {
    // "Me gusta". Antes esta URI caía en la rama genérica y acababa pidiendo
    // `GET /tracks/collection`, que devuelve 404: la lista de favoritos no sonaba nunca y
    // no había ningún error visible, simplemente silencio.
    const { data } = await axios.get<TrackOut[]>('/library/liked');
    const lista = data.map(toTrack);
    if (!lista.length) return;
    const pos = Math.min(offset, lista.length - 1);
    colaController.cargar(lista, 'liked', pos, trackUri);
    await playerController.play(lista[pos]);
    return;
  }

  if (kind === 'track') {
    if (uris.length > 1) {
      // Lista entera (una tabla de canciones): la cola queda rellena con el resto.
      const lista = await resolvLista(uris);
      const primero = lista[Math.min(offset, Math.max(0, lista.length - 1))];
      if (!primero) {
        playerController.resume();
        return;
      }
      const pos = lista.indexOf(primero);
      colaController.cargar(lista, 'player', pos, body.context_uri ?? null);
      await playerController.play(primero);
      return;
    }
    const track = await getTrackProf(id);
    if (track) await playerController.play(track, 'search');
    return;
  }

  if (kind === 'album') {
    const [artist, album] = id.split('::');
    const { data } = await axios.get<TrackOut[]>('/tracks', { params: { artist, album } });
    const lista = data.map(toTrack);
    if (!lista.length) return;
    const pos = Math.min(offset, lista.length - 1);
    // La URI del contexto se guarda para que la página del álbum sepa que es la que suena.
    colaController.cargar(lista, 'album', pos, `radiopv:album:${id}`);
    await playerController.play(lista[pos]);
    return;
  }

  if (kind === 'playlist') {
    const { data } = await axios.get<TrackOut[]>(`/playlists/${id}/tracks`);
    const lista = data.map(toTrack);
    if (!lista.length) return;
    const pos = Math.min(offset, lista.length - 1);
    colaController.cargar(lista, `playlist:${id}`, pos, `radiopv:playlist:${id}`);
    await playerController.play(lista[pos]);
    return;
  }

  // Mix de «Hecho para ti» (`radiopv:mix:radar`): las canciones las sirve el servidor, que es el
  // único que sabe cuáles componen el mix y en qué orden. Antes esta URI caía en la rama genérica
  // y acababa pidiendo una canción con id «mix», así que pulsar reproducir en una tarjeta de
  // «Hecho para ti» no sonaba.
  if (kind === 'mix') {
    const { data } = await axios.get<TrackOut[]>(`/mixes/${encodeURIComponent(id)}/tracks`);
    const lista = data.map(toTrack);
    if (!lista.length) return;
    const pos = Math.min(offset, lista.length - 1);
    colaController.cargar(lista, `mix:${id}`, pos, trackUri);
    await playerController.play(lista[pos]);
    return;
  }

  // Artista: sus canciones más escuchadas, para que el botón grande del artista suene.
  if (kind === 'artist') {
    const { data } = await axios.get<TrackOut[]>(`/artists/${encodeURIComponent(id)}/top`);
    const lista = data.map(toTrack);
    if (!lista.length) return;
    const pos = Math.min(offset, lista.length - 1);
    colaController.cargar(lista, 'artist', pos, `radiopv:artist:${id}`);
    await playerController.play(lista[pos]);
    return;
  }

  const track = await getTrackProf(id);
  if (track) await playerController.play(track, 'player');
};

// Comandos que ahora controlan nuestro <audio> + la cola del cliente.
const pausePlayback = async () => { playerController.pause(); };
const seekToPosition = async (position_ms: number) => { playerController.seek(position_ms / 1000); };
const nextTrack = async () => { colaController.siguiente(false); };
const previousTrack = async () => { colaController.anterior(); };

// Fire-and-forget transport command. Targets our SDK device (so it doesn't depend on a
// pre-existing "active device") and never throws on a transient failure — e.g. a stray
// `onChangeEnd` fired during a React StrictMode unmount, or no active device yet. This keeps a
// failed control call from surfacing as an uncaught 404 in the UI.
const playerCommand = async (
  method: 'put' | 'post',
  url: string,
  params?: Record<string, string | number | boolean>
) => {
  try {
    await axios[method](url, {}, { params: { ...deviceParams(), ...params } });
  } catch (e) {
    console.warn(`Spotify player command failed: ${method.toUpperCase()} ${url}`, e);
  }
};

/**
 * @description Set the repeat mode for the user's playback. This API only works for users who have Spotify Premium.
 * @param state track, context, or off. track will repeat the current track. context will repeat the current context. off will turn repeat off.
 */
const setRepeatMode = async (_state: 'track' | 'context' | 'off') => {
  colaController.repetir(_state === 'track' ? 2 : _state === 'context' ? 1 : 0);
};

/**
 * @description Set the volume for the user’s current playback device. This API only works for users who have Spotify Premium.
 * @param volume_percent The volume to set. Must be a value from 0 to 100 inclusive.
 */
const setVolume = async (volume_percent: number) => { playerController.volume(volume_percent); };

/**
 * @description Volumen actual del reproductor, en 0..1. Lo usa el deslizador de la barra
 * de reproducción para arrancar con el volumen real en vez de dar por hecho 100%.
 */
const getVolume = (): number => playerController.getVolume();

/**
 * @description Toggle shuffle on or off for user’s playback. This API only works for users who have Spotify Premium.
 */
const toggleShuffle = async (_state: boolean) => { colaController.barajar(_state); };

/**
 * Resuelve una URI de contexto a su lista de canciones: playlist, álbum, artista o "me gusta".
 * Devuelve `[]` (y no lanza) si la URI no es un contexto reconocible.
 */
const tracksDeContexto = async (uri: string): Promise<Track[]> => {
  const parts = String(uri).split(':');
  const kind = parts[1];
  // Igual que en `startPlayback`: la clave del álbum lleva `::`, así que hay que quedarse con
  // todo lo que sigue al tipo y no con el último trozo.
  const id = parts.slice(2).join(':');
  try {
    if (kind === 'user' && parts[parts.length - 1] === 'collection') {
      const { data } = await axios.get<TrackOut[]>('/library/liked');
      return data.map(toTrack);
    }
    if (kind === 'playlist') {
      const { data } = await axios.get<TrackOut[]>(`/playlists/${id}/tracks`);
      return data.map(toTrack);
    }
    if (kind === 'album') {
      const [artist, album] = id.split('::');
      const { data } = await axios.get<TrackOut[]>('/tracks', { params: { artist, album } });
      return data.map(toTrack);
    }
    if (kind === 'artist') {
      const { data } = await axios.get<TrackOut[]>(`/artists/${encodeURIComponent(id)}/top`);
      return data.map(toTrack);
    }
  } catch {
    /* contexto no reconocido: se ignora */
  }
  return [];
};

/**
 * @description Añade una lista entera (playlist, álbum, artista o "me gusta") al final de la cola.
 *
 * `addToQueue` sólo entiende canciones sueltas: le pasábamos la URI de la playlist y acababa
 * pidiendo `GET /tracks/{id-de-playlist}`, que da 404, así que la opción estaba directamente
 * desactivada en los menús de playlist y de álbum. Aquí se resuelven todas sus canciones.
 */
const addContextToQueue = async (uri: string) => {
  const lista = await tracksDeContexto(uri);
  if (lista.length) colaController.encolar(lista);
  return lista.length;
};

/**
 * @description Add an item to the end of the user's current playback queue. This API only works for users who have Spotify Premium.
 */
const addToQueue = async (uri: string) => {
  // Si la URI es de una lista, se encola la lista entera en vez de intentar resolverla como
  // si fuera una única canción.
  if (/^radiopv:(playlist|album|artist):/.test(uri) || /^spotify:user:.*:collection$/.test(uri)) {
    return void addContextToQueue(uri);
  }
  const track = await getTrackProf(tidDeUri(uri));
  if (track) colaController.encolar([track]);
};

/** "Añadir a continuación": se inserta justo tras la canción que suena (B1). */
const addToQueueNext = async (uri: string) => {
  const track = await getTrackProf(tidDeUri(uri));
  if (track) colaController.añadirAContinuacion([track]);
};

/** Quita de la cola la canción que ocupa esa posición (el panel de la cola tiene una X). */
const removeFromQueue = async (indice: number) => { colaController.quitar(indice); };

/** Reordena la cola moviendo una canción de una posición a otra. */
const moveInQueue = async (desde: number, hasta: number) => { colaController.mover(desde, hasta); };

/** Vacía lo que queda por sonar, sin cortar la canción actual. */
const clearQueue = async () => { colaController.vaciar(); };

/** Lanza el "Flow": encadena canciones parecidas a la última que ha sonado. */
const startFlow = async () => { colaController.lanzarFlow(); };

/**
 * @description Get tracks from the current user's recently played tracks. Note: Currently doesn't support podcast episodes.
 */
const getRecentlyPlayed = async (params: { limit?: number; after?: number; before?: number } = {}) => {
  const { data } = await axios.get<TrackOut[]>('/library/history', { params: { limit: params.limit ?? 50 } });
  // Mapea a la forma PlayHistoryObject que espera home.ts ({track, context}).
  const items = data.map((t) => ({
    track: toTrack(t),
    played_at: '',
    context: {
      type: t.album ? 'album' : 'artist',
      uri: `radiopv:${t.album ? 'album' : 'artist'}:${t.album ? `${t.artist}::${t.album}` : t.artist}`,
    },
  }));
  return { items };
};

export const playerService = {
  addToQueue,
  addContextToQueue,
  addToQueueNext,
  removeFromQueue,
  moveInQueue,
  clearQueue,
  startFlow,
  setPlaybackDevice,
  setPlaybackDeviceName,
  fetchPlaybackState,
  transferPlayback,
  startPlayback,
  pausePlayback,
  nextTrack,
  previousTrack,
  setRepeatMode,
  setVolume,
  getVolume,
  toggleShuffle,
  seekToPosition,
  getRecentlyPlayed,
  getAvailableDevices,
};
