import axios from '../axios';

import type { Track } from '../interfaces/track';
import type { Album } from '../interfaces/albums';
import type { Artist } from '../interfaces/artist';
import type { Pagination } from '../interfaces/api';
import type { Playlist } from '../interfaces/playlists';
import { toTrack, toArtist, toAlbum, toPage, toPlaylist } from '../api/adapt';
import type { TrackOut, ArtistOut, PlaylistOut } from '../api/types';

const SEARCH_MAX_LIMIT = 20;
const clampLimit = (limit?: number) => Math.min(limit ?? SEARCH_MAX_LIMIT, SEARCH_MAX_LIMIT);

/** /tracks?q= y /artists?q= → objeto {albums, tracks, artists, playlists} que espera la búsqueda. */
export const querySearch = async (params: {
  q: string;
  type?: string;
  market?: string;
  limit?: number;
  offset?: number;
}) => {
  const limit = clampLimit(params.limit);
  const [tracksRes, artistsRes] = await Promise.all([
    axios.get<TrackOut[]>('/tracks', { params: { q: params.q, limit } }),
    axios.get<ArtistOut[]>('/artists', { params: { q: params.q, limit } }),
  ]);
  const tracks = tracksRes.data.map(toTrack);
  const artists = artistsRes.data.map(toArtist);
  // Total real desde X-Total-Count (el scroll infinito de Search lo usa para saber si hay más).
  const tracksTotal = Number(tracksRes.headers['x-total-count'] ?? tracksRes.data.length) || tracksRes.data.length;
  const artistsTotal = Number(artistsRes.headers['x-total-count'] ?? artistsRes.data.length) || artistsRes.data.length;
  // álbumes: derivar de los tracks (únicos por artist+album)
  const seen = new Set<string>();
  const albums: Album[] = [];
  for (const t of tracksRes.data) {
    const key = `${t.artist}::${t.album ?? ''}`;
    if (!t.album || seen.has(key)) continue;
    seen.add(key);
    albums.push(toAlbum({ artist: t.artist, title: t.album, year: t.year, cover_url: t.cover }));
  }
  const playlists = (
    (await axios.get<PlaylistOut[]>('/playlists/system', { params: { limit } })).data ?? []
  ).map((p) => toPlaylist(p));
  const mk = <T,>(items: T[], total: number, offset = 0) =>
    toPage(items, total, limit, offset) as unknown as Pagination<T>;
  return {
    data: {
      albums: mk(albums, albums.length, params.offset),
      tracks: mk(tracks, tracksTotal, params.offset),
      artists: mk(artists, artistsTotal, params.offset),
      playlists: mk(playlists, playlists.length, params.offset),
    },
  };
};

/** No hay podcasts/episodios en RadioPV. */
export const searchEpisodes = async (_params: { q: string; limit?: number; offset?: number; market?: string }) => {
  return { data: { episodes: toPage([], 0, 0, 0) } };
};
