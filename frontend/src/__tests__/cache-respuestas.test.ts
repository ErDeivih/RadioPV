import { describe, expect, it } from 'vitest';

import { esRespuestaCacheable } from '../axios';

/**
 * Qué respuestas se guardan en IndexedDB.
 *
 * Esto no es un detalle: se guardaban durante 24 HORAS, así que cachear algo que cambia deja la
 * pantalla con datos viejos un día entero. Pasó dos veces:
 *   · con las búsquedas: una búsqueda sin resultados se quedaba pegada todo el día;
 *   · con las listas: renombrabas una lista, el servidor lo guardaba bien, y la pantalla seguía
 *     enseñando el nombre viejo incluso recargando (y el propio refresco volvía a leer la copia
 *     vieja de la caché y la reponía).
 * Por eso el catálogo se cachea y las listas NO.
 */
const get = (url: string, params?: Record<string, unknown>) => ({ method: 'get', url, params });

describe('qué se guarda en la caché de respuestas', () => {
  it('el catálogo inmutable sí (ahorra peticiones y esperas)', () => {
    expect(esRespuestaCacheable(get('/tracks'))).toBe(true);
    expect(esRespuestaCacheable(get('/tracks', { limit: 50, offset: 0 }))).toBe(true);
    expect(esRespuestaCacheable(get('/tracks/1234'))).toBe(true);
    expect(esRespuestaCacheable(get('/artists/9'))).toBe(true);
    expect(esRespuestaCacheable(get('/artists'))).toBe(true);
  });

  it('las listas NUNCA (cambian al editarlas)', () => {
    expect(esRespuestaCacheable(get('/playlists'))).toBe(false);
    expect(esRespuestaCacheable(get('/playlists/system'))).toBe(false);
    expect(esRespuestaCacheable(get('/playlists/81'))).toBe(false);
    expect(esRespuestaCacheable(get('/playlists/81/tracks'))).toBe(false);
  });

  it('las búsquedas NUNCA (el «sin resultados» se quedaba pegado)', () => {
    expect(esRespuestaCacheable(get('/tracks', { q: 'rosalia' }))).toBe(false);
    expect(esRespuestaCacheable(get('/tracks', { search: 'rosalia' }))).toBe(false);
    expect(esRespuestaCacheable(get('/artists', { query: 'rosalia' }))).toBe(false);
  });

  it('las escrituras no se cachean', () => {
    expect(esRespuestaCacheable({ method: 'post', url: '/playlists' })).toBe(false);
    expect(esRespuestaCacheable({ method: 'patch', url: '/playlists/81' })).toBe(false);
    expect(esRespuestaCacheable({ method: 'put', url: '/playlists/81/cover' })).toBe(false);
    expect(esRespuestaCacheable({ method: 'delete', url: '/playlists/81' })).toBe(false);
  });

  it('lo que empieza igual pero no es lo mismo, tampoco', () => {
    // `/tracksXYZ` no es `/tracks`: el patrón antiguo lo habría dado por bueno con un `test` flojo.
    expect(esRespuestaCacheable(get('/tracksXYZ'))).toBe(false);
    expect(esRespuestaCacheable(get('/artistass'))).toBe(false);
    // Y las rutas de usuario no entran.
    expect(esRespuestaCacheable(get('/library/liked'))).toBe(false);
    expect(esRespuestaCacheable(get('/me/player'))).toBe(false);
  });
});
