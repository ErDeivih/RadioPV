import { describe, it, expect } from 'vitest';
import { toTrack, toArtist, toPage, toPlaylist } from '../api/adapt';
import { API_BASE } from '../apiBase';

const pista = {
  id: 42, title: 'Canción', artist: 'Artista', album: 'Álbum', year: 2020,
  era: '20s', genre: 'pop', language: 'es', bpm: 120, energy: 0.6,
  tags: 'fiesta', is_remix: false, explicit: true, duration: 185.4,
  cover: '/media/covers/1.jpg', feat: null, rank: 500000, gain_db: -3.2,
} as any;

describe('adapt · TrackOut → la forma que espera la interfaz', () => {
  it('convierte los segundos a milisegundos', () => {
    expect(toTrack(pista).duration_ms).toBe(185400);
  });
  it('el id viaja como texto y la uri es la nuestra', () => {
    const t = toTrack(pista);
    expect(t.id).toBe('42');
    expect(t.uri).toBe('radiopv:track:42');   // identificador interno: NO se renombra
  });
  it('conserva explicit y el artista', () => {
    const t = toTrack(pista);
    expect(t.explicit).toBe(true);
    expect(t.artists[0].name).toBe('Artista');
  });
  it('el álbum siempre lleva una imagen (aunque falte la carátula)', () => {
    expect(toTrack(pista).album.images.length).toBeGreaterThan(0);
    expect(toTrack({ ...pista, cover: null }).album.images[0].url).toBeTruthy();
  });
  it('pasa gain_db para que el reproductor iguale el volumen', () => {
    expect(toTrack(pista).radiopv.gain_db).toBe(-3.2);
  });
  it('no revienta con los campos opcionales vacíos', () => {
    const minimo = { id: 1, title: 'x', artist: 'y', is_remix: false, explicit: false } as any;
    expect(() => toTrack(minimo)).not.toThrow();
    expect(toTrack(minimo).duration_ms).toBe(0);
  });
});

describe('adapt · artistas y paginación', () => {
  it('el artista sin foto no rompe', () => {
    const a = toArtist({ id: 1, name: 'A', image: null } as any);
    expect(a.name).toBe('A');
    expect(Array.isArray(a.images)).toBe(true);
  });
  it('toPage calcula el enlace siguiente sólo si quedan elementos', () => {
    expect(toPage([1, 2], 10, 2, 0).next).toBeTruthy();
    expect(toPage([1, 2], 2, 2, 0).next).toBeNull();
    expect(toPage([1, 2], 10, 2, 0).previous).toBeNull();
  });
});

describe('adapt · listas', () => {
  const lista = { id: 7, name: 'Mi lista', description: '', type: 'user', n_tracks: 3, user_id: 5 } as any;

  it('el dueño es el de verdad, para poder saber si la lista es tuya', () => {
    expect(toPlaylist(lista).owner.id).toBe('5');
    // Las listas que genera la aplicación no tienen dueño: no son de nadie.
    expect(toPlaylist({ ...lista, user_id: null }).owner.id).toBe('radiopv');
  });

  it('la portada propia se pide pasando por la API (si no, la imagen sale rota)', () => {
    // La API devuelve rutas relativas `/media/covers/x`, pero quien las sirve es el contenedor de
    // la API: en producción, detrás de `/api`. Sin ese prefijo, nginx contesta el index.html de la
    // aplicación (con un 200), la imagen no carga y el análisis de color se queda sin hacer.
    // Se compara con API_BASE porque en las pruebas apunta a otro sitio que en producción
    // (`/api`): lo que importa es que el prefijo se ponga.
    const conFoto = toPlaylist({ ...lista, cover: '/media/covers/playlist-7-abc.jpg' } as any);
    expect(conFoto.images[0].url).toBe(`${API_BASE}/media/covers/playlist-7-abc.jpg`);
    expect(conFoto.images[0].url).not.toBe('/media/covers/playlist-7-abc.jpg');
  });

  it('sin portada propia siempre hay una imagen de relleno', () => {
    expect(toPlaylist({ ...lista, cover: null } as any).images[0].url).toBeTruthy();
  });

  it('la privacidad se refleja tal cual (antes iba a fuego a falso)', () => {
    expect(toPlaylist({ ...lista, public: true } as any).public).toBe(true);
    expect(toPlaylist(lista).public).toBe(false);
  });
});

describe('ganancia por canción', () => {
  const factor = (db: number) => Math.pow(10, db / 20);
  it('0 dB no cambia el volumen', () => expect(factor(0)).toBeCloseTo(1, 6));
  it('-6 dB es la mitad de amplitud', () => expect(factor(-6)).toBeCloseTo(0.5012, 3));
  it('-3 dB coincide con lo que verifica el e2e', () => expect(factor(-3)).toBeCloseTo(0.7079, 4));
});
