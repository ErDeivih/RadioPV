import { getToken, clearToken } from './api/token';
import { API_BASE } from './apiBase';
import Axios from 'axios';
import { message } from 'antd';
import { getFromLocalStorageWithExpiry } from './utils/localstorage';
import { cacheGet, cacheSet } from './utils/cache';

const path = API_BASE;   // ← era https://api.spotify.com/v1

const access_token = getToken() as string;

const axios = Axios.create({
  baseURL: path,
  headers: {},
});

if (access_token) {
  axios.defaults.headers.common['Authorization'] = 'Bearer ' + access_token;
}

// --- Global concurrency limiter --------------------------------------------------------------
// Several screens (Home, Artist) fan out many requests at once, and dev StrictMode doubles
// them. Spotify's tightened Feb-2026 rate limits 429 on those bursts. Cap how many requests are
// in flight at once so traffic is smoothed instead of bursted; the rest queue and drain as
// slots free up. Combined with the 429 backoff below, this keeps the app under the limit.
const MAX_CONCURRENT = 3;
let activeRequests = 0;
const waiters: Array<() => void> = [];

const acquireSlot = () =>
  new Promise<void>((resolve) => {
    if (activeRequests < MAX_CONCURRENT) {
      activeRequests++;
      resolve();
    } else {
      waiters.push(() => {
        activeRequests++;
        resolve();
      });
    }
  });

const releaseSlot = () => {
  activeRequests = Math.max(0, activeRequests - 1);
  waiters.shift()?.();
};

// --- IndexedDB response cache ----------------------------------------------------------------
// Catalog data (artists/albums/tracks) is immutable, so cache GETs of it in IndexedDB and serve
// from there on repeat views and across reloads. This is the real fix for the rate limiting:
// navigating back to a page, or hard-refreshing, no longer re-hits the network.
//
// SOLO el catálogo, que no cambia nunca. Las LISTAS se quedan FUERA a propósito: son datos del
// usuario y cambian cada vez que renombras una, le pones foto, le quitas una canción… Cachearlas
// 24 h tenía un efecto muy visible: guardabas el nombre nuevo, el servidor lo guardaba bien, y la
// pantalla seguía enseñando el viejo incluso después de recargar. Peor: el propio refresco
// (`refreshPlaylist`) volvía a pedir la lista, recibía la copia vieja de la caché y la volvía a
// poner en pantalla. Ojo, que `/playlists` también son las listas del sistema, y esas las
// reescribe el worker cada día, así que tampoco valen.
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // el catálogo es estático; 24h es seguro
const CACHEABLE_PATH = /^\/(tracks|artists)(\/|$)/;   // ← catálogo inmutable, nunca listas

/**
 * ¿Es una BÚSQUEDA? Las búsquedas nunca se cachean.
 *
 * El comentario de arriba ya decía que las búsquedas van siempre a la red, pero el código no lo
 * cumplía: `/tracks?q=...` encaja en CACHEABLE_PATH, así que la respuesta se guardaba 24 horas en
 * IndexedDB. El efecto real era que una búsqueda que devolvía «sin resultados» se quedaba pegada
 * todo el día: arreglar el buscador en el servidor no cambiaba nada en el navegador, y al usuario
 * le seguía pareciendo roto. (Pasó justo así al arreglar las tildes.)
 */
const esBusqueda = (config: any) =>
  ['q', 'search', 'query'].some((k) => (config.params ?? {})[k] != null);

const isCacheableGet = (config: any) =>
  (config.method || 'get').toLowerCase() === 'get' &&
  CACHEABLE_PATH.test(config.url || '') &&
  !esBusqueda(config);

/** Se exporta para poder probarlo: que las listas NO se cacheen es una regla fácil de romper. */
export const esRespuestaCacheable = isCacheableGet;

const cacheKeyFor = (config: any) =>
  `${config.url}?${JSON.stringify(config.params || {})}|hide_explicit=${
    localStorage.getItem('radiopv_hide_explicit') === '1' ? 1 : 0
  }`;

axios.interceptors.request.use(async (config) => {
  await acquireSlot();

  if (isCacheableGet(config)) {
    const key = cacheKeyFor(config);
    const entry = await cacheGet(key);
    if (entry && entry.expiry > Date.now()) {
      // Cache hit — short-circuit the network by serving from a one-off adapter. The response
      // still flows through the response interceptor below (so the slot is released normally).
      (config as any).adapter = async () => ({
        data: entry.data,
        status: 200,
        statusText: 'OK (cache)',
        headers: {},
        config,
        request: {},
      });
    } else {
      // Mark for storing once the network response comes back.
      (config as any).__cacheKey = key;
    }
  }

  // FE-10/D2 · perfil familiar: si está activo "ocultar explícito", pedir explicit=false al
  // servidor en TODAS las listas que lo aceptan (nunca filtrar en el cliente, que rompería
  // X-Total-Count y el scroll infinito).
  const url = (config.url || '') as string;
  const explicitPaths = /^\/(tracks(\/|$)|recommend(\/(daily|radio|trending))?(\/|$)|playlists\/\d+\/tracks(\/|$)|library\/(liked|history)(\/|$)|artists\/[^/]+\/top(\/|$))/;
  if (localStorage.getItem('radiopv_hide_explicit') === '1' && explicitPaths.test(url)) {
    config.params = { ...(config.params || {}), explicit: false };
  }

  return config;
});

axios.interceptors.response.use(
  (response) => {
    releaseSlot();

    const key = (response.config as any).__cacheKey;
    if (key && response.status === 200) {
      void cacheSet(key, { data: response.data, expiry: Date.now() + CACHE_TTL_MS });
    }
    return response;
  },
  async (error) => {
    // Release this attempt's slot first so a retry (and other queued requests) can proceed.
    releaseSlot();

    const response = error?.response;
    const config = error?.config;

    // Network error / no response — nothing to recover from.
    if (!response || !config) return Promise.reject(error);

    if (response.status === 401) {
      // Sesión caducada: no hacer el OAuth de Spotify. Limpiar el token y dejar que la app
      // vuelva a pedir login (el slice de auth observa el token al montar).
      clearToken();
      localStorage.removeItem('stream_token');
      delete axios.defaults.headers.common['Authorization'];
      return Promise.reject(error);
    }

    // 429 Too Many Requests: Spotify's tightened (Feb 2026) rate limits are easy to trip when
    // a page fires a burst of calls (and dev StrictMode doubles them). Back off for the
    // server-specified `Retry-After`, then retry — bounded so we never loop forever.
    if (response.status === 429) {
      config.__retryCount = (config.__retryCount || 0) + 1;
      // Only one retry: during a global cooldown, re-issuing many times just adds load and
      // prolongs the penalty window.
      if (config.__retryCount > 1) return Promise.reject(error);
      const retryAfter = Number(response.headers?.['retry-after']);
      const waitMs = Math.min((Number.isFinite(retryAfter) ? retryAfter : 1) * 1000, 10000);
      await new Promise((resolve) => setTimeout(resolve, Math.max(waitMs, 500)));
      return axios(config);
    }

    // F5 · Error visible: un toast cuando el backend falla (5xx), en vez del silencio actual.
    if (response.status >= 500) {
      message.error('Error al cargar los datos. Inténtalo de nuevo.');
    }

    return Promise.reject(error);
  }
);

export default axios;
