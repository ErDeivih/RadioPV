import { playerController } from './playerController';
import axios from '../axios';
import { toTrack } from '../api/adapt';
import type { TrackOut } from '../api/types';
import type { Track } from '../interfaces/track';

/** Cola de reproducción del cliente (RadioPV).
 *
 *  Se rellena al arrancar un contexto (álbum, playlist, lista de canciones → `uris`) y la
 *  consume el evento `ended` — `bindEnded(() => colaController.siguiente(true))` en webPlayback —
 *  o el botón "siguiente".
 *
 *  Cuando la cola se agota entra el "Flow" (10_FRONTEND_SPEC §4.6): en vez de parar pedimos
 *  `GET /recommend/radio?seed_track={última}` y encadenamos los vecinos por similitud.
 *
 *  Es un módulo-singleton (como playerController): lo usan webPlayback (provider) y playerService
 *  (comandos), sin pasarlo por React. */

type ColaItem = Track;

const RADIO_N = 25;                 // cuántas canciones de radio pedimos de una vez
const CONTEXTO_RADIO = 'radio';     // contexto de las señales de escucha mientras encadena

let cola: ColaItem[] = [];                       // siguientes canciones
let fuente: ColaItem[] = [];                     // lista original (para repeat = context)
let historial: ColaItem[] = [];                  // canciones ya sonadas (para "anterior")
let actual: ColaItem | null = null;              // canción que suena ahora
let contexto = 'player';                         // contexto para las señales de escucha
let repetir: 0 | 1 | 2 = 0;                      // 0 off · 1 context · 2 track
let barajando = false;
let ultimoId: string | null = null;              // id de la última canción (semilla del Flow)
/** URI del contexto que está sonando (`radiopv:playlist:12`, `radiopv:album:x::y`…).
 *  Sin esto la UI no puede saber si la playlist que estás viendo es la que suena, así que el
 *  botón grande nunca se ponía en "pausa" ni marcaba el contexto activo. */
let uriContexto: string | null = null;
let pidiendoRadio = false;                       // evita dos GET /recommend/radio simultáneos
let onChange: (() => void) | null = null;        // avisa a la UI (Redux) para volcar la cola (B1)

const REPEAT_KEY = 'radiopv_repeat';
try { repetir = (Number(localStorage.getItem(REPEAT_KEY)) as 0 | 1 | 2) || 0; } catch { /* ignore */ }

const cambios = () => {
  onChange?.();
  // Al cambiar aleatorio/repetir/cola hay que republicar el estado: si la música está en pausa
  // no llegan `timeupdate`s y los iconos de la barra se quedarían sin actualizar.
  playerController.refrescar();
};

const artistOf = (t: ColaItem) => t.artists?.[0]?.name;

/** Shuffle con separación de artistas (10_FRONTEND_SPEC §4.5): evita dos canciones del mismo
 *  artista seguidas, que suena mal. */
const barajar = (xs: ColaItem[]): ColaItem[] => {
  const r = [...xs].sort(() => Math.random() - 0.5);
  for (let i = 1; i < r.length; i++) {
    const a = artistOf(r[i]);
    const b = artistOf(r[i - 1]);
    if (a && a === b) {
      const j = r.findIndex((x, k) => k > i && artistOf(x) !== b);
      if (j > -1) [r[i], r[j]] = [r[j], r[i]];
    }
  }
  return r;
};

const reproducir = (item: ColaItem) => {
  void playerController.play(item, contexto);
  // B5: pre-buffear la siguiente (cola[0]) para que el salto no tenga silencio.
  // Con guarda: `precacheNext(undefined)` acababa pidiendo `/stream/undefined` y el error se
  // tragaba en silencio (una petición perdida por cada canción al final de la cola).
  const siguiente = cola[0]?.id;
  if (siguiente !== undefined && siguiente !== null) void playerController.precacheNext(siguiente);
};

// Al sonar una canción (da igual si viene de startPlayback o de la cola) registramos cuál es
// la actual, su historial y la semilla del "Flow". playerController avisa con `bindPlayed`.
playerController.bindPlayed((t) => {
  if (actual) historial.push(actual);
  actual = t as unknown as ColaItem;
  ultimoId = t.id;
});

/** "Flow" §4.6: al agotarse la cola seguimos con la radio del último tema. */
const cargarRadio = async () => {
  if (pidiendoRadio) return;
  if (!ultimoId) {
    playerController.detener();
    return;
  }
  pidiendoRadio = true;
  try {
    const { data } = await axios.get<TrackOut[]>('/recommend/radio', {
      params: { seed_track: ultimoId, n: RADIO_N },
    });
    const items = data.map(toTrack).filter((t) => t.id !== ultimoId); // no repetir el seed
    if (items.length) {
      contexto = CONTEXTO_RADIO;
      cola.push(...items);
      const sig = cola.shift()!;
      reproducir(sig);
    } else {
      // No hay nada más: se para de verdad. Sin esto el elemento quedaba en estado de error
      // con `paused = false`, o sea la interfaz decía que estaba sonando algo que no sonaba.
      playerController.detener();
    }
  } catch {
    // Sin backend/red el flujo simplemente se detiene (no es un error de la UI).
    playerController.detener();
  } finally {
    pidiendoRadio = false;
  }
};

const avanzar = (auto: boolean) => {
  // repeat = track: al terminar sola, vuelve a sonar la misma.
  if (auto && repetir === 2 && actual) {
    reproducir(actual);
    cambios();
    return;
  }
  const sig = cola.shift();
  if (sig) {
    reproducir(sig);
    cambios();
    return;
  }
  // Cola agotada.
  if (repetir === 1 && fuente.length) {
    cola = barajando ? barajar(fuente) : [...fuente];
    const first = cola.shift();
    if (first) {
      reproducir(first);
      cambios();
      return;
    }
  }
  void cargarRadio();               // sigue sonando aunque la cola se acabe
};

export const colaController = {
  setContexto(c: string) { contexto = c; },
  /** Rellena la cola al arrancar un contexto. `lista` es el orden completo (fuente), `offset` es
   *  el índice de la canción que ya estamos reproduciendo (se excluye de la cola).
   *  `uri` es la URI del contexto que suena (playlist/álbum/…), para que la UI sepa cuál es. */
  cargar(lista: ColaItem[], ctx?: string, offset = 0, uri?: string | null) {
    fuente = lista;
    contexto = ctx ?? contexto;
    uriContexto = uri ?? null;
    actual = null;                  // nuevo contexto → historial y "anterior" empiezan de cero
    historial = [];
    const resto = lista.slice(offset + 1);
    cola = barajando ? barajar(resto) : [...resto];
    cambios();
  },
  encolar(items: ColaItem[]) { cola.push(...items); cambios(); },
  /** "Añadir a continuación": se inserta justo tras la canción actual, no al final. */
  añadirAContinuacion(items: ColaItem[]) { cola.splice(0, 0, ...items); cambios(); },
  /** Avanza a la siguiente canción. `auto = true` viene del evento `ended` (respeta repeat=track);
   *  `false` es el botón "siguiente" (siempre salta). */
  siguiente(auto = true) { avanzar(auto); },
  anterior() {
    const pos = playerController.position();
    if (pos > 3) {                 // si lleva más de 3 s, "anterior" reinicia el tema
      playerController.seek(0);
      void playerController.resume();
      cambios();
      return;
    }
    const prev = historial.pop();
    if (prev) reproducir(prev);
    else {
      playerController.seek(0);
      void playerController.resume();
    }
    cambios();
  },
  repetir(mode: 0 | 1 | 2) {
    repetir = mode;
    try { localStorage.setItem(REPEAT_KEY, String(mode)); } catch { /* ignore */ }
    cambios();
  },
  barajar(on: boolean) {
    barajando = on;
    if (on) cola = barajar(cola);
    cambios();
  },
  limpiar() {
    cola = [];
    fuente = [];
    historial = [];
    actual = null;
    uriContexto = null;
    cambios();
  },
  bindChange(fn: (() => void) | null) { onChange = fn; },
  get cola() { return cola; },
  get actual() { return actual; },
  get shuffle() { return barajando; },
  get repeat() { return repetir; },
  get uriContexto() { return uriContexto; },
};

export type { ColaItem };
