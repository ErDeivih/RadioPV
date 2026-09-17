import { describe, it, expect, vi, beforeEach } from 'vitest';

/*
 * Volumen al arrancar el reproductor.
 *
 * `ensure()` lee el volumen guardado UNA sola vez, al crear el elemento de audio, así que para
 * probar cada caso hace falta un módulo recién importado: de eso se encarga `vi.resetModules()`
 * antes de cada prueba.
 *
 * El fallo que se protege aquí (el que hacía que en el móvil "no se escuchara nada"):
 *
 *     const vol = Number(localStorage.getItem(VOLUME_KEY));
 *     if (!Number.isNaN(vol)) audio.volume = ...
 *
 * Sin nada guardado, `getItem` devuelve `null` y `Number(null)` es 0 — y 0 NO es NaN, así que la
 * condición se cumplía y el volumen quedaba en CERO. La canción avanzaba, el deslizador marcaba
 * 100 % y no se oía absolutamente nada.
 */

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
  resume() { return Promise.resolve(); }
  close() { return Promise.resolve(); }
}

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
  addEventListener() { /* nada */ }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
  load() { /* nada */ }
}

let creados: AudioFalso[] = [];

(globalThis as any).AudioContext = AudioContextFalso;
(globalThis as any).webkitAudioContext = AudioContextFalso;
(globalThis as any).Audio = function AudioDoble() {
  const a = new AudioFalso();
  creados.push(a);
  return a;
} as any;
globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) })) as any;

vi.mock('../api/stream', () => ({
  streamUrl: vi.fn(async (id: string | number) => `blob:falso/${id}`),
  invalidarStreamToken: vi.fn(),
}));

const pista = {
  id: '1', uri: 'radiopv:track:1', name: 'Canción', duration_ms: 200000,
  artists: [{ name: 'Artista' }], album: { name: 'Álbum', images: [{ url: 'c.jpg' }] },
  radiopv: { gain_db: 0 },
} as any;

/** Importa el reproductor de cero y devuelve el elemento de audio que ha creado. */
const arrancarDeCero = async () => {
  vi.resetModules();
  creados = [];
  const { playerController } = await import('../player/playerController');
  await playerController.play(pista, 'player');
  return { audio: creados[0], playerController };
};

describe('volumen inicial del reproductor', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('sin nada guardado suena al 100 %, no en mudo', async () => {
    const { audio, playerController } = await arrancarDeCero();
    // El caso que fallaba: antes quedaba en 0 (silencio total) con la interfaz marcando 100 %.
    expect(audio.volume).toBe(1);
    expect(playerController.getVolume()).toBe(1);
  });

  it('respeta un volumen guardado normal', async () => {
    localStorage.setItem('radiopv_volume', '0.35');
    const { audio } = await arrancarDeCero();
    expect(audio.volume).toBeCloseTo(0.35, 5);
  });

  it('respeta el 0 explícito: si el usuario lo dejó en mudo, sigue en mudo', async () => {
    localStorage.setItem('radiopv_volume', '0');
    const { audio, playerController } = await arrancarDeCero();
    // Distinguir "no hay nada guardado" de "el usuario lo puso a 0" es justo el arreglo.
    expect(audio.volume).toBe(0);
    expect(playerController.getVolume()).toBe(0);
  });

  it('un valor guardado corrupto no deja el reproductor en mudo', async () => {
    localStorage.setItem('radiopv_volume', 'no-es-un-numero');
    const { audio } = await arrancarDeCero();
    expect(audio.volume).toBe(1);
  });

  it('la interfaz lee el volumen real del audio, no uno supuesto', async () => {
    localStorage.setItem('radiopv_volume', '0.8');
    const { audio, playerController } = await arrancarDeCero();
    expect(playerController.getVolume()).toBeCloseTo(audio.volume, 5);
  });
});
