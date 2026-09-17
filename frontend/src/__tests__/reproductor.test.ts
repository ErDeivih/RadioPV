import { describe, it, expect, beforeEach, vi } from 'vitest';

/*
 * Pruebas del reproductor y de la cola.
 *
 * El reproductor y la cola son singletons de módulo con efectos reales (crean un <audio>, un
 * AudioContext y piden el token de streaming por red). Aquí se sustituyen esas tres cosas para
 * poder comprobar la LÓGICA, que es donde estaban los fallos que se han corregido:
 *
 *   · `emit()` no publicaba `paused`/`position`/`duration`, los campos que lee toda la interfaz.
 *   · `shuffle`/`repeat_mode` se publicaban fijos a `false`/`0`, así que los botones de aleatorio
 *     y repetir nunca reflejaban el estado real.
 *   · `Number(localStorage.getItem('radiopv_volume'))` daba 0 (y no NaN) sin nada guardado, o sea
 *     volumen CERO en un móvil recién estrenado.
 *   · la URI del contexto no se guardaba, así que ningún botón sabía qué playlist sonaba.
 *
 * `jsdom` no implementa `HTMLMediaElement.play()` (lanza "Not implemented") ni `AudioContext`,
 * por eso se parchean antes de importar los módulos.
 */

// --- dobles de prueba -------------------------------------------------------------------------
class GainFalso {
  gain = { value: 1 };
  connect() { return this; }
}
class NodoFalso {
  connect() { return this; }
  addEventListener() { /* nada */ }
}
class AudioContextFalso {
  state = 'running';
  destination = {};
  createMediaElementSource() { return new NodoFalso(); }
  createGain() { return new GainFalso(); }
  resume() { this.state = 'running'; return Promise.resolve(); }
  close() { return Promise.resolve(); }
}

/** Eventos registrados por el reproductor, para poder dispararlos desde el test. */
const oyentes = new Map<string, Array<() => void>>();

class AudioFalso {
  src = '';
  crossOrigin = '';
  preload = '';
  volume = 1;
  muted = false;
  paused = true;
  ended = false;
  currentTime = 0;
  duration = 0;
  error: { code: number } | null = null;
  addEventListener(tipo: string, fn: () => void) {
    const lista = oyentes.get(tipo) ?? [];
    lista.push(fn);
    oyentes.set(tipo, lista);
  }
  play() { this.paused = false; this.disparar('play'); return Promise.resolve(); }
  pause() { this.paused = true; this.disparar('pause'); }
  load() { /* nada */ }
  disparar(tipo: string) { (oyentes.get(tipo) ?? []).forEach((fn) => fn()); }
}

let ultimoAudio: AudioFalso | null = null;

/**
 * El reproductor es un singleton: `ensure()` crea el `<audio>` UNA sola vez por módulo.
 * Cada `new Audio()` devuelve una instancia NUEVA, porque el reproductor crea una segunda para
 * pre-cargar la siguiente canción: si compartieran instancia, la precarga pisaría el `src` de la
 * que está sonando. Se recuerda la PRIMERA, que es el elemento real de reproducción.
 * Los oyentes NO se limpian entre pruebas: los registró `ensure()` y sin ellos no llegarían los
 * eventos `play`/`pause`/`timeupdate`.
 */
let principal: AudioFalso | null = null;

const dameAudio = (): AudioFalso => principal!;

/** Espera a que se resuelvan las promesas encadenadas (play es asíncrono). */
const esperar = () => new Promise((r) => setTimeout(r, 0));

/** Pista en el formato que devuelve la API (`TrackOut`), para el doble de `axios`. */
const trackOut = (id: number) => ({
  id, title: `Canción ${id}`, artist: 'Artista', album: 'Álbum', year: 2020,
  era: '20s', genre: 'pop', language: 'es', bpm: 120, energy: 0.5, tags: '',
  is_remix: false, explicit: false, duration: 200, cover: null, feat: null,
  rank: 1, gain_db: 0,
});

vi.mock('../api/stream', () => ({
  streamUrl: vi.fn(async (id: string | number) => `blob:falso/${id}`),
  invalidarStreamToken: vi.fn(),
}));

vi.mock('../axios', () => ({
  default: {
    get: vi.fn(async (url: string) => {
      // Catálogo mínimo: /tracks/{id}, /playlists/{id}/tracks y /library/liked.
      const una = /^\/tracks\/(\d+)$/.exec(url);
      if (una) return { data: trackOut(Number(una[1])) };
      if (/^\/playlists\/\d+\/tracks$/.test(url)) return { data: [1, 2, 3].map(trackOut) };
      if (url === '/library/liked') return { data: [7, 8].map(trackOut) };
      if (url === '/tracks') return { data: [1, 2, 3].map(trackOut) };
      if (/^\/artists\/.*\/top$/.test(url)) return { data: [4, 5].map(trackOut) };
      return { data: [] };
    }),
    post: vi.fn(async () => ({ data: {} })),
  },
}));

// Debe asignarse ANTES de importar los módulos que las usan.
(globalThis as any).AudioContext = AudioContextFalso;
(globalThis as any).webkitAudioContext = AudioContextFalso;
(globalThis as any).Audio = function AudioDoble() {
  const elemento = new AudioFalso();
  if (!principal) principal = elemento;      // el primero es el <audio> del reproductor
  ultimoAudio = elemento;
  return elemento;
} as any;
globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) })) as any;

const { playerController } = await import('../player/playerController');
const { colaController } = await import('../player/queueController');
const { playerService } = await import('../services/player');

// --- utilidades -------------------------------------------------------------------------------
const pista = (id: number, artista = `Artista ${id}`) => ({
  id: String(id),
  uri: `radiopv:track:${id}`,
  name: `Canción ${id}`,
  duration_ms: 200000,
  artists: [{ name: artista }],
  album: { name: 'Álbum', images: [{ url: 'cover.jpg' }] },
  radiopv: { gain_db: 0 },
}) as any;

/** Estado publicado por el reproductor (lo último que recibió el puente). */
let estado: any = null;

const arrancar = async (track = pista(1)) => {
  estado = null;
  playerController.bind((s) => { estado = s; });
  // El elemento lo crea `ensure()` dentro de `play()`: sólo se puede leer DESPUÉS.
  if (principal) {
    principal.paused = true;
    principal.ended = false;
    principal.currentTime = 0;
    principal.duration = 0;
    principal.error = null;
  }
  await playerController.play(track, 'playlist:7');
  return dameAudio();
};

describe('reproductor · contrato de estado que lee la interfaz', () => {
  beforeEach(() => {
    localStorage.clear();
    colaController.limpiar();
  });

  it('publica `paused`, que es lo que decide si el botón dice play o pausa', async () => {
    const audio = await arrancar();
    expect(estado).not.toBeNull();
    expect(estado.paused).toBe(false);
    expect(estado.is_playing).toBe(true);

    audio.pause();
    expect(estado.paused).toBe(true);
    expect(estado.is_playing).toBe(false);
  });

  it('publica `position` y `duration` en milisegundos, y también la forma `_ms`', async () => {
    const audio = await arrancar();
    audio.duration = 210.5;
    audio.currentTime = 42.25;
    audio.disparar('timeupdate');

    expect(estado.position).toBe(42250);
    expect(estado.duration).toBe(210500);
    // La forma de la Web API se mantiene por compatibilidad.
    expect(estado.position_ms).toBe(42250);
    expect(estado.duration_ms).toBe(210500);
  });

  it('con la duración aún desconocida no publica NaN (la barra desaparecía)', async () => {
    const audio = await arrancar();
    audio.duration = NaN;
    audio.currentTime = 3;
    audio.disparar('timeupdate');
    expect(Number.isFinite(estado.duration)).toBe(true);
    expect(estado.duration).toBe(0);
  });

  it('sin canción cargada no se está reproduciendo (el icono no debe mentir)', async () => {
    // `state` nulo en la interfaz equivale a `!state && ...`: se comprueba el valor publicado.
    const audio = await arrancar();
    audio.pause();
    expect(estado.is_playing).toBe(false);
  });
});

describe('reproductor · volumen y búsqueda', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('sin volumen guardado el volumen es 1, NO 0 (era el fallo del silencio en el móvil)', async () => {
    const audio = await arrancar();
    // `Number(null)` es 0, y la comprobación `!Number.isNaN(vol)` lo aceptaba: sonaba en mudo.
    expect(audio.volume).toBe(1);
    expect(playerController.getVolume()).toBe(1);
  });

  // El volumen guardado se comprueba en `volumen-guardado.test.ts`: `ensure()` lo lee UNA sola
  // vez, al crear el elemento, así que aquí ya no se puede cambiar.

  it('guarda el volumen al cambiarlo', async () => {
    const audio = await arrancar();
    playerController.volume(60);
    expect(audio.volume).toBeCloseTo(0.6, 5);
    expect(localStorage.getItem('radiopv_volume')).toBe('0.6');
  });

  it('seek mueve la posición y sube el estado a la interfaz', async () => {
    const audio = await arrancar();
    audio.duration = 100;
    playerController.seek(30);
    audio.disparar('timeupdate');
    expect(audio.currentTime).toBe(30);
    expect(estado.position).toBe(30000);
  });
});

describe('cola · reproducción de listas, siguiente/anterior, aleatorio y repetición', () => {
  beforeEach(() => {
    localStorage.clear();
    colaController.limpiar();
    colaController.repetir(0);
    colaController.barajar(false);
    colaController.setContexto('player');
  });

  it('cargar() rellena la cola con el resto y recuerda la URI del contexto', () => {
    const lista = [pista(1), pista(2), pista(3)];
    colaController.cargar(lista, 'playlist:7', 0, 'radiopv:playlist:7');
    expect(colaController.cola.map((t) => t.id)).toEqual(['2', '3']);
    // Sin esto, el botón grande de la playlist nunca sabía que era la que estaba sonando.
    expect(colaController.uriContexto).toBe('radiopv:playlist:7');
  });

  it('empezando por el índice 2 la cola son las siguientes, no todas', () => {
    const lista = [pista(1), pista(2), pista(3), pista(4)];
    colaController.cargar(lista, 'playlist:7', 2, 'radiopv:playlist:7');
    // Pulsar la fila 3 debe dejar en cola la 4 (antes sonaba siempre la 1).
    expect(colaController.cola.map((t) => t.id)).toEqual(['4']);
  });

  it('siguiente saca la primera de la cola y la pone a sonar', async () => {
    const lista = [pista(1), pista(2), pista(3)];
    colaController.cargar(lista, 'playlist:7', 0, 'radiopv:playlist:7');
    await playerController.play(lista[0]);
    colaController.siguiente(false);
    await esperar();
    expect(colaController.actual?.id).toBe('2');
    expect(colaController.cola.map((t) => t.id)).toEqual(['3']);
  });

  it('anterior con más de 3 s vuelve a empezar la canción en vez de saltar', async () => {
    const audio = await arrancar(pista(1));
    colaController.cargar([pista(1), pista(2)], 'playlist:7', 0, 'radiopv:playlist:7');
    await playerController.play(pista(1));
    audio.currentTime = 40;
    colaController.anterior();
    expect(audio.currentTime).toBe(0);
  });

  it('aleatorio se puede encender Y apagar (antes siempre se encendía)', () => {
    colaController.cargar([pista(1), pista(2), pista(3)], 'playlist:7', 0, 'radiopv:playlist:7');
    colaController.barajar(true);
    expect(colaController.shuffle).toBe(true);
    expect(colaController.cola).toHaveLength(2);
    colaController.barajar(false);
    // El botón mandaba `!shuffle` y el estado publicado era siempre `false`, así que sólo se
    // podía activar, nunca desactivar.
    expect(colaController.shuffle).toBe(false);
  });

  it('repetir cicla off → contexto → canción y se recuerda', () => {
    colaController.repetir(1);
    expect(colaController.repeat).toBe(1);
    colaController.repetir(2);
    expect(colaController.repeat).toBe(2);
    expect(localStorage.getItem('radiopv_repeat')).toBe('2');
    colaController.repetir(0);
    expect(colaController.repeat).toBe(0);
  });

  it('repetir canción: al terminar sola vuelve a sonar la misma', async () => {
    const audio = await arrancar(pista(1));
    colaController.cargar([pista(1), pista(2)], 'playlist:7', 0, 'radiopv:playlist:7');
    await playerController.play(pista(1));
    colaController.repetir(2);
    colaController.siguiente(true);      // auto = true (viene del evento `ended`)
    await esperar();
    expect(colaController.actual?.id).toBe('1');
    expect(audio.src).toContain('/1');
  });

  it('repetir contexto: agotada la cola se vuelve a llenar desde la lista original', async () => {
    const lista = [pista(1), pista(2)];
    colaController.cargar(lista, 'playlist:7', 0, 'radiopv:playlist:7');
    await playerController.play(lista[0]);
    colaController.repetir(1);
    colaController.siguiente(false);     // suena la 2, cola vacía
    await esperar();
    expect(colaController.actual?.id).toBe('2');
    expect(colaController.cola).toHaveLength(0);
    colaController.siguiente(true);      // se agota → debe recargar la lista
    await esperar();
    expect(colaController.actual?.id).toBe('1');
  });

  it('"añadir a continuación" mete la canción justo detrás de la actual', () => {
    colaController.cargar([pista(1), pista(2), pista(3)], 'playlist:7', 0, 'radiopv:playlist:7');
    colaController.añadirAContinuacion([pista(99)]);
    expect(colaController.cola.map((t) => t.id)).toEqual(['99', '2', '3']);
  });

  it('limpiar() deja la cola y el contexto vacíos', () => {
    colaController.cargar([pista(1)], 'playlist:7', 0, 'radiopv:playlist:7');
    colaController.limpiar();
    expect(colaController.cola).toHaveLength(0);
    expect(colaController.uriContexto).toBeNull();
  });
});

describe('servicio · playlists, álbumes y favoritos', () => {
  beforeEach(() => {
    localStorage.clear();
    colaController.limpiar();
    colaController.repetir(0);
    colaController.barajar(false);
  });

  it('una lista de uris arranca por el offset indicado y deja el resto en cola', async () => {
    const uris = ['radiopv:track:1', 'radiopv:track:2', 'radiopv:track:3'];
    await playerService.startPlayback({ uris, offset: { position: 2 } });
    // uris[2] es la tercera: antes sonaba siempre la primera, fuera cual fuera la pulsada.
    expect(colaController.actual?.id).toBe('3');
    await playerService.startPlayback({ uris, offset: { position: 1 } });
    expect(colaController.actual?.id).toBe('2');
    // Queda por sonar la última.
    expect(colaController.cola.map((t) => t.id)).toEqual(['3']);
  });

  it('una playlist carga sus canciones y recuerda su contexto', async () => {
    await playerService.startPlayback({ context_uri: 'radiopv:playlist:7' });
    expect(colaController.actual?.id).toBe('1');
    expect(colaController.uriContexto).toBe('radiopv:playlist:7');
    expect(colaController.cola.map((t) => t.id)).toEqual(['2', '3']);
  });

  it('un álbum arranca por el índice pedido', async () => {
    await playerService.startPlayback({
      context_uri: 'radiopv:album:Artista::Álbum',
      offset: { position: 2 },
    });
    expect(colaController.actual?.id).toBe('3');
    expect(colaController.uriContexto).toBe('radiopv:album:Artista::Álbum');
  });

  it('"me gusta" suena de verdad (antes pedía /tracks/collection y daba 404)', async () => {
    await playerService.startPlayback({ context_uri: 'spotify:user:1:collection' });
    expect(colaController.actual?.id).toBe('7');
    expect(colaController.cola.map((t) => t.id)).toEqual(['8']);
    expect(colaController.uriContexto).toBe('spotify:user:1:collection');
  });

  it('el botón grande de un artista suena con sus canciones más escuchadas', async () => {
    await playerService.startPlayback({ context_uri: 'radiopv:artist:Rosalía' });
    expect(colaController.actual?.id).toBe('4');
    expect(colaController.cola.map((t) => t.id)).toEqual(['5']);
  });

  it('añadir una lista entera a la cola encola todas sus canciones', async () => {
    colaController.limpiar();
    const n = await playerService.addContextToQueue('radiopv:playlist:7');
    expect(n).toBe(3);
    expect(colaController.cola.map((t) => t.id)).toEqual(['1', '2', '3']);
  });

  it('la cola se puede consultar sin llamar a un endpoint que no existe', async () => {
    await playerService.startPlayback({ context_uri: 'radiopv:playlist:7' });
    const { userService } = await import('../services/users');
    const { data } = await userService.fetchQueue();
    // Antes: GET /me/player/queue → 404 silencioso en cada apertura del panel.
    expect(data.queue.map((t: any) => t.id)).toEqual(['2', '3']);
    expect((data.currently_playing as any).id).toBe('1');
  });
});

describe('canciones cuyo archivo no está en el servidor', () => {
  beforeEach(() => {
    localStorage.clear();
    colaController.limpiar();
    colaController.repetir(0);
    colaController.barajar(false);
  });

  /** El servidor responde 410 al pedir el stream: el fichero no existe. */
  const servidorSinFichero = () => {
    (globalThis.fetch as any).mockImplementation(async (url: string) => {
      if (String(url).startsWith('blob:falso')) return { status: 410, ok: false };
      return { ok: true, status: 200, json: async () => ({}) };
    });
  };

  it('avisa en pantalla y salta a la siguiente en vez de quedarse clavada', async () => {
    const audio = await arrancar(pista(1));
    colaController.cargar([pista(1), pista(2), pista(3)], 'playlist:7', 0, 'radiopv:playlist:7');
    await playerController.play(pista(1));
    playerController.bindEnded(null);
    playerController.bindFallo(() => colaController.siguiente(false));

    const avisos: string[] = [];
    const escucha = (e: Event) => avisos.push((e as CustomEvent<{ mensaje: string }>).detail.mensaje);
    window.addEventListener('radiopv:aviso', escucha);

    servidorSinFichero();
    audio.error = { code: 4 };            // MEDIA_ERR_SRC_NOT_SUPPORTED
    audio.disparar('error');
    await esperar();

    window.removeEventListener('radiopv:aviso', escucha);

    // Antes: el elemento quedaba con `paused = false`, sin sonido y con el tiempo en 0:00 para
    // siempre. La playlist parecía muerta y no había ningún mensaje.
    expect(avisos.length).toBeGreaterThan(0);
    expect(avisos[0]).toContain('Canción 1');
    expect(colaController.actual?.id).toBe('2');
    expect(colaController.cola.map((t) => t.id)).toEqual(['3']);
  });

  it('no repite la canción que falta aunque la repetición esté en "una sola"', async () => {
    const audio = await arrancar(pista(1));
    colaController.cargar([pista(1), pista(2)], 'playlist:7', 0, 'radiopv:playlist:7');
    await playerController.play(pista(1));
    colaController.repetir(2);            // repetir la canción actual
    playerController.bindFallo(() => colaController.siguiente(false));

    servidorSinFichero();
    audio.error = { code: 4 };
    audio.disparar('error');
    await esperar();
    // Con `onEnded` (auto = true) se habría vuelto a pedir la misma que falta: bucle infinito.
    expect(colaController.actual?.id).toBe('2');
  });

  it('con el token caducado (401) reintenta en vez de saltarse la canción', async () => {
    const audio = await arrancar(pista(1));
    colaController.cargar([pista(1), pista(2)], 'playlist:7', 0, 'radiopv:playlist:7');
    await playerController.play(pista(1));
    let saltos = 0;
    playerController.bindFallo(() => { saltos++; });

    (globalThis.fetch as any).mockImplementation(async (url: string) => {
      if (String(url).startsWith('blob:falso')) return { status: 401, ok: false };
      return { ok: true, status: 200, json: async () => ({}) };
    });
    audio.error = { code: 3 };            // MEDIA_ERR_DECODE
    audio.disparar('error');
    await esperar();
    // Un 401 es token caducado, no fichero ausente: la canción sigue siendo la misma.
    expect(saltos).toBe(0);
    expect(colaController.actual?.id).toBe('1');
  });
});
