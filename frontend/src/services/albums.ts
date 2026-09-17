import axios from '../axios';

import type { Track } from '../interfaces/track';
import type { Album } from '../interfaces/albums';
import type { Pagination, PaginationQueryParams } from '../interfaces/api';
import { toTrack, toAlbum, toPage } from '../api/adapt';
import type { TrackOut } from '../api/types';

/** id de álbum en RadioPV = `artista::álbum` (no hay entidad "álbum" propia). */
const splitKey = (id: string): [string, string] => {
  const i = id.indexOf('::');
  return i === -1 ? [id, ''] : [id.slice(0, i), id.slice(i + 2)];
};

const fetchNewRelases = async (_params: PaginationQueryParams = {}) => {
  // No hay "novedades" fijas; podrían ir de /recommend/trending. Dejamos vacío para ocultar la fila.
  const empty = { items: [], total: 0, limit: 0, offset: 0, next: null, previous: null } as unknown as Pagination<Album>;
  return { data: { albums: empty } };
};

const fetchAlbum = async (id: string) => {
  const [artist, album] = splitKey(id);
  const { data } = await axios.get<TrackOut[]>('/tracks', { params: { artist, album } });
  const tracks = data.map(toTrack);
  const albumObj = toAlbum({ artist, title: album, year: data[0]?.year, cover_url: data[0]?.cover });
  // total_tracks por defecto es 0 en toAlbum; la cabecera usa el nº real de pistas.
  albumObj.total_tracks = tracks.length;
  return { data: { ...albumObj, tracks } as unknown as Album & { tracks: Track[] } };
};

const fetchAlbums = async (ids: string[]) => {
  const responses = await Promise.all(ids.map((id) => fetchAlbum(id)));
  return { ...responses[0], data: { albums: responses.map((r) => r.data) } };
};

const fetchAlbumTracks = async (id: string, params: PaginationQueryParams = {}) => {
  const [artist, album] = splitKey(id);
  const { data } = await axios.get<TrackOut[]>('/tracks', { params: { artist, album } });
  const items = data.map(toTrack);
  const page = toPage(items, items.length, params.limit ?? items.length, params.offset ?? 0);
  return { data: page as unknown as Pagination<Track> };
};

const fetchSavedAlbums = async (params: PaginationQueryParams = {}) => {
  const { data } = await axios.get<TrackOut[]>('/library/liked');
  const seen = new Set<string>();
  const items = [];
  for (const t of data) {
    const key = `${t.artist}::${t.album ?? ''}`;
    if (!t.album || seen.has(key)) continue;
    seen.add(key);
    items.push({ added_at: '', album: toAlbum({ artist: t.artist, title: t.album, year: t.year, cover_url: t.cover }) });
  }
  const page = toPage(items, items.length, params.limit ?? items.length, params.offset ?? 0);
  return { data: page as unknown as Pagination<{ added_at: string; album: Album }> };
};

const saveAlbums = async (_ids: string[]) => ({ data: true });
const deleteAlbums = async (_ids: string[]) => ({ data: true });

export const albumsService = {
  fetchAlbum,
  fetchAlbums,
  fetchNewRelases,
  fetchSavedAlbums,
  fetchAlbumTracks,
  saveAlbums,
  deleteAlbums,
};
