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
/** Siguiente / anterior desde la pantalla de bloqueo (MediaSession). La cola vive en
 *  `queueController`, así que el reproductor sólo guarda la función que le pasa el puente. */
let onNext: (() => void) | null = null;
let onPrev: (() => void) | null = null;
/** Qué hacer cuando una canción no se puede cargar (fichero ausente). Distinto de `onEnded`
 *  porque aquí hay que saltar SIEMPRE: si no, con la repetición en "una sola canción" se
 *  volvería a pedir la misma que falta y entraría en un bucle. */
let onFallo: (() => void) | null = null;
let precarga: HTMLAudioElement | null = null;   // audio oculto que pre-buffea la siguiente (B5)

const VOLUME_KEY = 'radiopv_volume';            // volumen persistente entre sesiones (B4)

/**
 * Volumen guardado, en 0..1.
 *
 * Si no hay nada guardado devuelve 1, NO 0. Y esto era un fallo de verdad, no un detalle:
 * antes aquí ponía `Number(localStorage.getItem(VOLUME_KEY))` y se comprobaba con
 * `!Number.isNaN(vol)`. En un móvil recién estrenado no hay nada guardado, `getItem`
 * devuelve `null` y **`Number(null)` es 0** (no NaN), así que la condición se cumplía y
 * el volumen se ponía a CERO. Resultado: la canción avanzaba, el deslizador marcaba 100%
 * y no se oía absolutamente nada. Hay que distinguir "no hay nada guardado" de
 * "el usuario lo dejó a 0" — sólo lo primero significa "pon el volumen normal".
 */
const volumenGuardado = (): number => {
  try {
    const bruto = localStorage.getItem(VOLUME_KEY);
    if (bruto === null || bruto.trim() === '') return 1;
    const v = Number(bruto);
    if (!Number.isFinite(v)) return 1;
    return Math.max(0, Math.min(1, v));
  } catch {
    return 1;                                   // modo privado o almacenamiento bloqueado
  }
};

/**
 * DESBLOQUEO DEL AUDIO EN EL MÓVIL
 * --------------------------------
 * En iOS y Android el navegador solo deja sonar si el primer `play()` del elemento ocurre
 * DENTRO de un gesto del usuario (un toque). Y aquí había un problema de fondo: en `play()`
 * se hace `audio.src = await streamUrl(id)` — un salto de red — y después `audio.play()`.
 * Cuando llega ese segundo play, el gesto ya se ha consumido, así que el navegador lo
 * RECHAZA y no suena nada. Sin error visible: simplemente silencio.
 *
 * La solución estándar es desbloquear el elemento una vez, con el primer toque en cualquier
 * parte de la app: se reproduce un WAV de silencio, se pausa, y a partir de ahí el elemento
 * queda habilitado para toda la sesión, aunque el play() llegue después de un await.
 *
 * Se aprovecha el mismo toque para reanudar el AudioContext, que en el móvil también nace
 * suspendido y sin él la ganancia por `gain_db` devuelve silencio.
 */
const SILENCIO_WAV =
  'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';

let desbloqueado = false;

const desbloquear = () => {
  if (desbloqueado) return;
  desbloqueado = true;
  document.removeEventListener('pointerdown', desbloquear, true);
  document.removeEventListener('touchend', desbloquear, true);
  document.removeEventListener('keydown', desbloquear, true);
  try {
    void ctx?.resume();
    if (!audio) return;
    const p = audio.play();
    if (p && typeof p.then === 'function') {
      p.then(() => audio!.pause()).catch(() => undefined);
    }
  } catch { /* si no se puede, el play() normal lo intentará igual */ }
};

/** Desbloquea el audio y deja escuchando el primer toque. */
const prepararDesbloqueo = () => {
  document.addEventListener('pointerdown', desbloquear, true);
  document.addEventListener('touchend', desbloquear, true);
  document.addEventListener('keydown', desbloquear, true);
};

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
  // El src de silencio deja el elemento listo para el desbloqueo del primer toque.
  audio.src = SILENCIO_WAV;
  ctx = new AudioContext();
  const src = ctx.createMediaElementSource(audio);
  gain = ctx.createGain();
  src.connect(gain);
  gain.connect(ctx.destination);
  prepararDesbloqueo();

  audio.addEventListener('timeupdate', () => {
    // Acumular solo el tiempo que avanza de verdad (ignora los saltos del seek).
    const t = audio!.currentTime;
    if (t > ultimoTick && t - ultimoTick < 2) escuchados += t - ultimoTick;
    ultimoTick = t;
    emit();
  });
  audio.addEventListener('play', () => { mediaSessionEstado(true); emit(); });
  // `playing` (no `play`) es el que se dispara cuando YA hay datos sonando: es el único momento
  // en el que se puede dar por buena la canción. Si se reiniciara el contador en `play`, el
  // cortafuegos de canciones no disponibles no serviría de nada, porque `play` también se dispara
  // cuando el fichero no existe.
  audio.addEventListener('playing', () => { fallosSeguidos = 0; });
  audio.addEventListener('pause', () => { mediaSessionEstado(false); emit(); });
  audio.addEventListener('ended', () => {
    cerrar(true);
    emit();
    // D4 · "parar al acabar la canción": no encadenar la siguiente.
    if (sleepEndOfSong) { sleepEndOfSong = false; return; }
    onEnded?.();               // deja que la cola avance (o el "Flow" encadene la radio)
  });
  // Sin esto, un 401 por token caducado o un 410 por fichero ausente son invisibles.
  // `alFallar` distingue los dos casos: reintenta el token o salta a la siguiente canción.
  audio.addEventListener('error', () => { void alFallar(); });

  // B4: recuperar el volumen guardado (ver `volumenGuardado`: sin nada guardado sonaba a 0).
  audio.volume = volumenGuardado();
};

const emit = () => {
  if (!onState || !audio || !current) return;
  const duracion = Number.isFinite(audio.duration) ? audio.duration : 0;
  const posicion = audio.currentTime;
  onState({
    track_window: { current_track: current },
    // ── CONTRATO DE ESTADO ──────────────────────────────────────────────────────────────
    // La UI lee la forma del SDK de Spotify (la que está declarada en `Spotify.PlaybackState`),
    // NO la de la Web API. Antes aquí sólo se publicaban `is_playing`/`position_ms`/`duration_ms`
    // y faltaban `paused`, `position` y `duration`, que es lo que consultan los componentes.
    // El resultado eran tres fallos que parecían independientes y eran el mismo:
    //   · `state.spotify.state?.paused` era `undefined` y `!undefined === true`, así que TODOS
    //     los botones de play/pausa creían estar sonando: sólo pausaban, nunca reanudaban.
    //   · la barra de progreso leía `position`/`duration` (inexistentes) → siempre 0:00 y al
    //     arrastrarla hacía seek a 0.
    // Se publican las dos formas (la del SDK y la de la API) para no romper a nadie.
    paused: audio.paused,
    is_playing: !audio.paused && !audio.ended,
    position: Math.round(posicion * 1000),
    duration: Math.round(duracion * 1000),
    position_ms: Math.round(posicion * 1000),
    duration_ms: Math.round(duracion * 1000),
    progress_ms: Math.round(posicion * 1000),
    timestamp: Date.now(),
    // La UI lee estos campos para habilitar/reflejar los botones (si faltan, `disallows.x` rompe).
    // `seeking` y `loading` no son disallows reales: el elemento ya está cargado.
    disallows: {
      pausing: false,
      resuming: false,
      skipping_next: false,
      skipping_prev: false,
      seeking: false,
    },
    // `shuffle`, `repeat_mode` y `context` los añade el puente (`webPlayback`) porque dependen
    // de la cola, y el reproductor no puede importarla sin crear un ciclo.
    shuffle: false,
    repeat_mode: 0,
    context: null,
  });
};

/** Vuelve a publicar el estado sin esperar al siguiente `timeupdate`.
 *  Hace falta al pulsar aleatorio/repetir con la música en pausa: sin `timeupdate` la UI no se
 *  enteraría del cambio y el icono se quedaría sin actualizar. */
const refrescar = () => emit();

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
  // Faltaban estos tres: en el móvil, los botones de la pantalla de bloqueo y de los
  // auriculares (siguiente / anterior / ±10 s) no hacían absolutamente nada.
  navigator.mediaSession.setActionHandler('nexttrack', () => onNext?.());
  navigator.mediaSession.setActionHandler('previoustrack', () => onPrev?.());
  navigator.mediaSession.setActionHandler('seekbackward', (d) => {
    if (audio) audio.currentTime = Math.max(0, audio.currentTime - (d.seekOffset ?? 10));
  });
  navigator.mediaSession.setActionHandler('seekforward', (d) => {
    if (audio) audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + (d.seekOffset ?? 10));
  });
};

/** Refleja en la pantalla de bloqueo si está sonando o en pausa (el icono del sistema). */
const mediaSessionEstado = (sonando: boolean) => {
  try {
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = sonando ? 'playing' : 'paused';
  } catch { /* algunos navegadores no dejan cambiarlo */ }
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

/* ─── CANCIONES SIN FICHERO ──────────────────────────────────────────────────────────────────
 *
 * El catálogo tiene más canciones que archivos de audio en el servidor, así que muchas devuelven
 * 410 al pedir el stream. El comportamiento anterior era nefasto: el elemento quedaba en estado
 * de error (`MEDIA_ERR_SRC_NOT_SUPPORTED`) con `paused = false`, o sea "reproduciendo" sin sonar
 * y con el tiempo parado en 0:00 PARA SIEMPRE. Desde fuera eso se ve como "la playlist no
 * suena": pulsabas el botón grande y no pasaba absolutamente nada, ni un mensaje.
 *
 * Ahora, cuando una canción no se puede cargar, se avisa y se pasa a la siguiente (como hace
 * Spotify con las no disponibles). Sólo se distinguen dos casos porque el elemento de audio no
 * expone el código HTTP: se pregunta al servidor por el mismo fichero.
 */

let fallosSeguidos = 0;              // canciones seguidas que no se han podido cargar
let recuperaciones = 0;              // reintentos por token caducado para la canción actual
const MAX_FALLOS_SEGUIDOS = 15;      // cortafuegos por si la radio encadena sólo no disponibles

/** Evento con el que el reproductor pide a la interfaz que muestre un aviso. */
export const AVISO = 'radiopv:aviso';

const avisar = (mensaje: string) => {
  try {
    window.dispatchEvent(new CustomEvent(AVISO, { detail: { mensaje } }));
  } catch { /* sin ventana (pruebas) no hay nada que avisar */ }
};

/** Motivo del fallo, preguntando al servidor por el mismo fichero. */
const causaDelFallo = async (): Promise<'permiso' | 'ausente' | 'desconocido'> => {
  if (!audio || !audio.src) return 'desconocido';
  try {
    const r = await fetch(audio.src, { headers: { Range: 'bytes=0-0' } });
    if (r.status === 401 || r.status === 403) return 'permiso';   // token caducado
    if (r.status === 404 || r.status === 410) return 'ausente';   // el fichero no está
    return 'desconocido';
  } catch {
    return 'desconocido';
  }
};

const alFallar = async () => {
  if (!audio || !current || recuperando) return;
  // Código 1 = MEDIA_ERR_ABORTED, que provocamos nosotros al cambiar de canción: no es un fallo.
  if (audio.error && audio.error.code === 1) return;

  const causa = await causaDelFallo();
  if (causa !== 'ausente' && recuperaciones < 1) {
    recuperaciones++;                 // puede ser el token: se reintenta una vez
    await recuperar();
    return;
  }

  fallosSeguidos++;
  const titulo = current.name;
  if (fallosSeguidos > MAX_FALLOS_SEGUIDOS) {
    avisar(
      'Se han saltado varias canciones seguidas: faltan sus archivos de audio en el servidor.'
    );
    audio.pause();
    return;
  }
  avisar(
    causa === 'ausente'
      ? `«${titulo}» no está en el servidor: se salta a la siguiente.`
      : `No se pudo reproducir «${titulo}»: se salta a la siguiente.`
  );
  cerrar(false);                       // deja constancia de la escucha parcial
  // Salta siempre (auto = false): con la repetición en "una sola canción" repetir la misma que
  // falta sería un bucle infinito.
  if (onFallo) onFallo();
  else onEnded?.();
};

export const playerController = {
  bind(onStateFn: ((s: unknown) => void) | null) { onState = onStateFn; },
  /** La cola (o el "Flow") se engancha aquí para encadenar la siguiente canción. */
  bindEnded(fn: (() => void) | null) { onEnded = fn; },
  /** Siguiente / anterior desde la pantalla de bloqueo o los auriculares. */
  bindNext(fn: (() => void) | null) { onNext = fn; },
  bindPrev(fn: (() => void) | null) { onPrev = fn; },
  /** Qué hacer si una canción no se puede cargar (normalmente: saltar a la siguiente). */
  bindFallo(fn: (() => void) | null) { onFallo = fn; },
  /** Republica el estado ya mismo (para que la UI reaccione sin esperar al `timeupdate`). */
  refrescar,
  /** Notifica a la cola qué canción acaba de sonar (mantiene `actual` y la semilla del Flow). */
  bindPlayed(fn: ((t: Track) => void) | null) { onPlayed = fn; },

  play: async (track: any, contexto = 'player') => {
    ensure();
    // ⚠️ `resume()` Y `desbloquear()` ANTES de cualquier await: tras un await de red el
    // navegador ya no considera que estemos dentro del gesto del usuario (Safari/iOS lo
    // rechaza). Por eso el desbloqueo va aquí arriba y no antes del `audio.play()`.
    void ctx!.resume();
    desbloquear();

    cerrar(false);                       // cierra la canción anterior con sus segundos
    current = track;
    contextoActual = contexto;
    escuchados = 0; ultimoTick = 0; cerrado = false;
    recuperaciones = 0;                  // reintentos de token: se cuentan por canción

    gain!.gain.value = Math.pow(10, (track?.radiopv?.gain_db ?? 0) / 20);
    audio!.src = await streamUrl(track.id);
    // El ctx puede haberse suspendido mientras se pedía el token (sobre todo si el móvil
    // se quedó en segundo plano). Se reanuda otra vez antes de sonar.
    void ctx!.resume();
    try {
      await audio!.play();
    } catch (e) {
      // Si el navegador lo rechaza por política de reproducción, no se puede arreglar desde
      // aquí: hace falta otro toque. Se deja constancia en vez de fallar en silencio.
      console.warn('No se pudo iniciar la reproducción:', e);
      throw e;
    }
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
  /** Volumen actual en 0..1. La interfaz lo usa para arrancar reflejando el volumen real
   *  en vez de suponer 100% (que es lo que hacía que el deslizador mintiera). */
  getVolume: () => (audio ? audio.volume : volumenGuardado()),
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
