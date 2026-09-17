import { getToken, setToken, clearToken } from '../api/token';
import { streamUrl, invalidarStreamToken } from '../api/stream';
import { API_BASE } from '../apiBase';

/** Controlador global de reproducción: un solo <audio> con ganancia por `gain_db`, MediaSession,
 *  señales de escucha y recuperación ante token caducado.
 *  Lo usan webPlayback (provider de estado) y playerService (comandos). */
const API = API_BASE;
const auth = () => ({ Authorization: `Bearer ${getToken()}` });

/* eslint-disable @typescript-eslint/no-explicit-any */
type Track = {
  id: string; name: string;
  artists: { name: string }[];
  album: { name: string; images: { url: string }[] };
  radiopv?: { gain_db?: number };
};

let audio: HTMLAudioElement | null = null;
let ctx: AudioContext | null = null;
let gain: GainNode | null = null;
let current: Track | null = null;
let onState: ((state: unknown) => void) | null = null;
let onEnded: (() => void) | null = null;
let onPlayed: ((track: Track) => void) | null = null;
let precarga: HTMLAudioElement | null = null;   // audio oculto que pre-buffea la siguiente (B5)

const VOLUME_KEY = 'radiopv_volume';            // volumen persistente entre sesiones (B4)

let contextoActual = 'player';   // "playlist:12" | "radio:88" | "daily" | "search" | "artist"
let escuchados = 0;              // segundos realmente escuchados de la canción actual
let ultimoTick = 0;
let cerrado = false;             // evita mandar la señal de cierre dos veces
let recuperando = false;         // evita bucles de recarga
let sleepTimer: number | null = null;   // D4 · temporizador de apagado (por tiempo)
let sleepEndOfSong = false;             // D4 · parar al acabar la canción

const ensure = () => {
  if (audio) return;
  audio = new Audio();
  // ⚠️ 'anonymous', NUNCA 'use-credentials': con credenciales el elemento queda
  // "tainted" y createMediaElementSource devolvería SILENCIO sin error claro.
  audio.crossOrigin = 'anonymous';
  audio.preload = 'auto';
  ctx = new AudioContext();
  const src = ctx.createMediaElementSource(audio);
  gain = ctx.createGain();
  src.connect(gain);
  gain.connect(ctx.destination);

  audio.addEventListener('timeupdate', () => {
    // Acumular solo el tiempo que avanza de verdad (ignora los saltos del seek).
    const t = audio!.currentTime;
    if (t > ultimoTick && t - ultimoTick < 2) escuchados += t - ultimoTick;
    ultimoTick = t;
    emit();
  });
  audio.addEventListener('play', emit);
  audio.addEventListener('pause', emit);
  audio.addEventListener('ended', () => {
    cerrar(true);
    emit();
    // D4 · "parar al acabar la canción": no encadenar la siguiente.
    if (sleepEndOfSong) { sleepEndOfSong = false; return; }
    onEnded?.();               // deja que la cola avance (o el "Flow" encadene la radio)
  });
  // Sin esto, un 401 por token caducado o un 410 por fichero ausente son invisibles.
  audio.addEventListener('error', () => { void recuperar(); });

  // B4: recuperar el volumen guardado.
  const vol = Number(localStorage.getItem(VOLUME_KEY));
  if (!Number.isNaN(vol)) audio.volume = Math.max(0, Math.min(1, vol));
};

const emit = () => {
  if (!onState || !audio || !current) return;
  onState({
    track_window: { current_track: current },
    is_playing: !audio.paused && !audio.ended,
    position_ms: Math.round(audio.currentTime * 1000),
    duration_ms: Math.round((audio.duration || 0) * 1000),
    // La UI lee estos campos para habilitar/reflejar los botones (si faltan, `disallows.x` rompe).
    disallows: { pausing: false, resuming: false, skipping_next: false, skipping_prev: false },
    shuffle: false,
    repeat_mode: 0,
  });
};

const mediaSession = () => {
  if (!current || !('mediaSession' in navigator) || !audio) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: current.name,
    artist: current.artists[0]?.name,
    album: current.album.name,
    artwork: [{ src: current.album.images[0]?.url ?? '', sizes: '512x512', type: 'image/jpeg' }],
  });
  navigator.mediaSession.setActionHandler('play', () => void audio!.play());
  navigator.mediaSession.setActionHandler('pause', () => audio!.pause());
  navigator.mediaSession.setActionHandler('seekto', (d) => {
    if (audio && d.seekTime != null) audio.currentTime = d.seekTime;
  });
};

const signal = (body: Record<string, unknown>) => {
  if (!current) return;
  void fetch(`${API}/library/${current.id}/play`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...auth() },
    body: JSON.stringify({ source: 'player', context: contextoActual, ...body }),
  }).catch(() => undefined);
};

/** Señal de salto (B6): se manda al saltar una canción antes de llegar al 30 % (spec §4.4). */
const skipSignal = () => {
  if (!current) return;
  void fetch(`${API}/library/${current.id}/skip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...auth() },
    body: JSON.stringify({ skipped: true }),
  }).catch(() => undefined);
};

/** Señal de cierre: sin ella `plays.seconds_listened` queda vacío y toda la ponderación
 *  implícita de la personalización (W-02) se queda sin datos. */
const cerrar = (completo: boolean) => {
  if (cerrado || !current) return;
  cerrado = true;
  signal({ completed: completo ? 1 : 0, seconds_listened: Math.round(escuchados) });
  // Salto manual antes del 30 % → además cuenta como skip.
  if (!completo && audio) {
    const dur = audio.duration || 0;
    if (dur > 0 && audio.currentTime / dur < 0.3) skipSignal();
  }
};

/** El token va dentro de `audio.src`; si caduca (pausa larga) el siguiente rango da 401 y el
 *  audio muere sin avisar. Aquí se pide token nuevo y se recarga conservando la posición. */
const recuperar = async () => {
  if (!audio || !current || recuperando) return;
  recuperando = true;
  try {
    const pos = audio.currentTime;
    const sonaba = !audio.paused;
    invalidarStreamToken();
    audio.src = await streamUrl(current.id);
    audio.currentTime = pos;
    if (sonaba) await audio.play();
  } catch {
    /* si tampoco así, se queda parado: el error ya es visible en la consola */
  } finally {
    recuperando = false;
  }
};

export const playerController = {
  bind(onStateFn: ((s: unknown) => void) | null) { onState = onStateFn; },
  /** La cola (o el "Flow") se engancha aquí para encadenar la siguiente canción. */
  bindEnded(fn: (() => void) | null) { onEnded = fn; },
  /** Notifica a la cola qué canción acaba de sonar (mantiene `actual` y la semilla del Flow). */
  bindPlayed(fn: ((t: Track) => void) | null) { onPlayed = fn; },

  play: async (track: any, contexto = 'player') => {
    ensure();
    // ⚠️ `resume()` ANTES de cualquier await: tras un await de red el navegador ya no
    // considera que estamos dentro del gesto del usuario (Safari/iOS lo rechaza).
    void ctx!.resume();

    cerrar(false);                       // cierra la canción anterior con sus segundos
    current = track;
    contextoActual = contexto;
    escuchados = 0; ultimoTick = 0; cerrado = false;

    gain!.gain.value = Math.pow(10, (track?.radiopv?.gain_db ?? 0) / 20);
    audio!.src = await streamUrl(track.id);
    await audio!.play();
    mediaSession();
    signal({ completed: 0, seconds_listened: 0 });
    // Avisa a la cola de que esta canción ya suena (actualiza `actual` y la semilla del Flow).
    onPlayed?.(track);
  },

  pause: () => audio?.pause(),
  resume: () => { void ctx?.resume(); void audio?.play(); },
  seek: (t: number) => { if (audio) { audio.currentTime = t; ultimoTick = t; } },
  /** Posición actual en segundos (para que "anterior" sepa si reiniciar o retroceder). */
  position: () => audio?.currentTime ?? 0,
  volume: (pct: number) => {
    if (audio) audio.volume = Math.max(0, Math.min(1, pct / 100));
    try { localStorage.setItem(VOLUME_KEY, String(Math.max(0, Math.min(1, pct / 100)))); }
    catch { /* ignore */ }
  },
  /** B5: pre-buffear la siguiente canción en un <audio> oculto (mismo token → misma URL → cache).
   *  Llámalo cuando sepas cuál toca después (cola[0]). */
  precacheNext: async (id: string | number) => {
    try {
      if (!precarga) {
        precarga = new Audio();
        precarga.crossOrigin = 'anonymous';
        precarga.preload = 'auto';
      }
      precarga.src = await streamUrl(id);
      precarga.load();
    } catch { /* no pasa nada si no hay siguiente */ }
  },
  /** Salto manual: cuenta como escucha parcial (alimenta el skip de la personalización). */
  end: () => cerrar(false),
  /** D4 · Temporizador de apagado: parar en `min` minutos, o 'song' para parar al acabar. */
  setSleep: (min: number | 'song') => {
    if (sleepTimer) { window.clearTimeout(sleepTimer); sleepTimer = null; }
    sleepEndOfSong = false;
    if (min === 'song') { sleepEndOfSong = true; return; }
    sleepTimer = window.setTimeout(() => { audio?.pause(); sleepTimer = null; }, min * 60 * 1000);
  },
  cancelSleep: () => {
    if (sleepTimer) { window.clearTimeout(sleepTimer); sleepTimer = null; }
    sleepEndOfSong = false;
  },
};
