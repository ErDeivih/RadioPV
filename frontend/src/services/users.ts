import axios from '../axios';

import type { Track } from '../interfaces/track';
import type { Artist } from '../interfaces/artist';
import type { Pagination, PaginationQueryParams } from '../interfaces/api';
import { Episode } from '../interfaces/episode';
import { User } from '../interfaces/user';
import { PlaylistItem } from '../interfaces/playlists';
import { toPage, toPlaylistItem, toArtist, toTrack } from '../api/adapt';
import type { TrackOut, ArtistOut } from '../api/types';
import { colaController } from '../player/queueController';

interface FetchTopItemsParams extends PaginationQueryParams {
  /** @description Over what time frame the affinities are computed. Valid values: long_term (calculated from ~1 year of data and including all new data as it becomes available), medium_term (approximately last 6 months), short_term (approximately last 4 weeks). Default: medium_term */
  timeRange: 'long_term' | 'medium_term' | 'short_term';
}

// --- Feb 2026 library consolidation -----------------------------------------
// Per-type save/remove/follow + their `/contains` checks were replaced by a single
// `/me/library` surface keyed by Spotify URIs. These helpers let the existing
// id-based service functions keep their signatures while talking to the new API.
type LibraryType = 'track' | 'album' | 'artist' | 'playlist' | 'user' | 'episode';

const toUris = (ids: string[], type: LibraryType) => ids.map((id) => `spotify:${type}:${id}`);

const saveToLibrary = (uris: string[]) => axios.put('/me/library', { uris });

const removeFromLibrary = (uris: string[]) => axios.delete('/me/library', { data: { uris } });

const libraryContains = (uris: string[]) =>
  axios.get<boolean[]>('/me/library/contains', { params: { uris: uris.join(',') } });

/**
 * @description Get the current user's top  tracks based on calculated affinity.
 */
const fetchTopTracks = async (params: FetchTopItemsParams = {} as FetchTopItemsParams) => {
  // RadioPV: no hay /me/top/tracks. Usamos /library/top?type=tracks (lo más escuchado del usuario),
  // envuelto como Pagination<Track> que es lo que esperan el perfil y las recomendaciones.
  const { data } = await axios.get<{ type: string; items: TrackOut[] }>('/library/top', {
    params: { type: 'tracks', limit: params.limit ?? 25 },
  });
  const items = data.items.map(toTrack);
  const page = toPage(items, items.length, params.limit ?? 25, 0);
  return { data: page as unknown as Pagination<Track> };
};

/**
 * @description Get the current user's top artists based on calculated affinity.
 */
const fetchTopArtists = async (_params: FetchTopItemsParams = {} as FetchTopItemsParams) => {
  // RadioPV: no hay /me/top/artists. /library/top?type=artists devuelve [{name, count}].
  const { data } = await axios.get<{ type: string; items: { name: string; count: number }[] }>(
    '/library/top', { params: { type: 'artists', limit: _params.limit ?? 50 } }
  );
  return { data: { items: data.items } as unknown as Pagination<Artist> };
};

/**
 * @description Get the current user's followed artists.
 */
const fetchFollowedArtists = async (_params: PaginationQueryParams = {}) => {
  // RadioPV: /follows devuelve NOMBRES de artista; los resolvemos a Artist (una petición por
  // nombre, que son pocos). El endpoint de Spotify /me/following no existe en nuestra API.
  const { data } = await axios.get<string[]>('/follows');
  const artists: Artist[] = [];
  for (const name of data) {
    try {
      const a = (await axios.get<ArtistOut>(`/artists/${encodeURIComponent(name)}`)).data;
      artists.push(toArtist(a));
    } catch {
      /* seguir con el siguiente nombre */
    }
  }
  const page = toPage(artists, artists.length, _params.limit ?? 50, 0);
  return { data: { artists: page } };
};

/**
 * @description Get the list of objects that make up the user's queue.
 *
 * En RadioPV la cola vive en el cliente (`queueController`), no en el servidor: la pedíamos a
 * `GET /me/player/queue`, un endpoint que aquí no existe, así que cada llamada (al abrir el
 * panel de reproducción, en las acciones de álbum/playlist/canción) devolvía un 404 silencioso.
 * Ahora se lee del propio reproductor y no se hace ninguna petición.
 */
const fetchQueue = async () => {
  const actual = colaController.actual as unknown as Track | null;
  return {
    data: {
      currently_playing: (actual ?? null) as Track | Episode,
      queue: [...colaController.cola] as unknown as (Track | Episode)[],
    },
  };
};

/**
 * @description Check if one or more tracks is already saved in the current Spotify user's 'Your Music' library.
 */
const checkSavedTracks = async (ids: string[]) => {
  // RadioPV: /library/reactions devuelve {liked:[ids], skipped:[ids]} en una petición.
  // El endpoint /me/library/contains de Spotify no existe en nuestra API.
  const { data } = await axios.get<{ liked: number[]; skipped: number[] }>('/library/reactions');
  const set = new Set(data.liked.map(String));
  return { data: ids.map((id) => set.has(String(id))) };
};

/**
 * @description Save one or more tracks to the current user's 'Your Music' library.
 */
const saveTracks = async (ids: string[]) => {
  await Promise.all(ids.map((id) => axios.post(`/library/${id}/like`, { liked: true })));
  return { data: true };
};

/**
 * @description Remove one or more tracks from the current user's 'Your Music' library.
 */
const deleteTracks = async (ids: string[]) => {
  await Promise.all(ids.map((id) => axios.post(`/library/${id}/like`, { liked: false })));
  return { data: true };
};

/**
 * @description Check to see if the current user is following a specified playlist.
 */
const checkFollowedPlaylist = async (playlistId: string) => {
  return await libraryContains(toUris([playlistId], 'playlist')).catch(() => {
    return { data: false };
  });
};

/**
 * @description Check to see if the current user is following one or more artists or other Spotify users.
 */
const checkFollowingArtists = async (names: string[]) => {
  // RadioPV: /follows devuelve nombres; comparamos localmente (el endpoint de Spotify no existe).
  const { data } = await axios.get<string[]>('/follows');
  const set = new Set(data);
  return { data: names.map((n) => set.has(n)) };
};

/**
 * @description Check to see if the current user is following one or more other Spotify users.
 */
const checkFollowingUsers = async (ids: string[]) => {
  return await libraryContains(toUris(ids, 'user'));
};

/**
 * @description Get public profile information about a Spotify user.
 */
const getUser = async (id: string) => {
  // `/users/{id}` was removed Feb 2026 (only `/me` survives). Fail soft so callers such as
  // the playlist owner lookup don't reject their `Promise.all` — they fall back to the
  // playlist's embedded `owner` object instead.
  return await axios
    .get<User>(`/users/${id}`)
    .catch(() => ({ data: null as unknown as User }));
};

/**
 * @description Remove the current user as a follower of a playlist.
 */
const unfollowPlaylist = async (playlistId: string) => {
  return await removeFromLibrary(toUris([playlistId], 'playlist'));
};

/**
 * @description Add the current user as a follower of a playlist.
 */
const followPlaylist = async (playlistId: string) => {
  return await saveToLibrary(toUris([playlistId], 'playlist'));
};

/**
 * @description Add the current user as a follower of one or more artists or other Spotify users.
 */
const followArtists = async (names: string[]) => {
  await Promise.all(names.map((n) => axios.post(`/follows/${encodeURIComponent(n)}`)));
  return { data: true };
};

/**
 * @description Remove the current user as a follower of one or more artists or other Spotify users.
 */
const unfollowArtists = async (names: string[]) => {
  await Promise.all(names.map((n) => axios.delete(`/follows/${encodeURIComponent(n)}`)));
  return { data: true };
};

/**
 * @description Add the current user as a follower of one or more users or other Spotify users.
 */
const followUsers = async (ids: string[]) => {
  return await saveToLibrary(toUris(ids, 'user'));
};

/**
 * @description Remove the current user as a follower of one or more other Spotify users.
 */
const unfollowUsers = async (ids: string[]) => {
  return await removeFromLibrary(toUris(ids, 'user'));
};

/**
 * @description Get a list of the songs saved in the current Spotify user's 'Your Music' library.
 */
const getSavedTracks = async (params: PaginationQueryParams = {}) => {
  const { data } = await axios.get<TrackOut[]>('/library/liked');
  const items = data.map(toPlaylistItem);
  const total = items.length;
  const page = toPage(items, total, params.limit ?? total, params.offset ?? 0);
  return { data: page as unknown as Pagination<PlaylistItem> };
};

export const userService = {
  getUser,
  saveTracks,
  fetchQueue,
  deleteTracks,
  getSavedTracks,
  fetchTopArtists,
  fetchTopTracks,
  checkSavedTracks,
  followPlaylist,
  checkFollowingUsers,
  followUsers,
  unfollowUsers,
  fetchFollowedArtists,
  checkFollowedPlaylist,
  unfollowPlaylist,
  checkFollowingArtists,
  followArtists,
  unfollowArtists,
};
