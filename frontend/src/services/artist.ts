import axios from '../axios';

import type { Track } from '../interfaces/track';
import type { Album } from '../interfaces/albums';
import type { Artist } from '../interfaces/artist';
import type { Pagination } from '../interfaces/api';
import { toArtist, toTrack, toAlbum, toPage } from '../api/adapt';
import type { ArtistOut, TrackOut } from '../api/types';

/** En RadioPV un artista se identifica por NOMBRE (ver api/adapt.ts::toArtist). */
const fetchArtist = (id: string) =>
  axios.get<ArtistOut>(`/artists/${encodeURIComponent(id)}`).then((r) => ({ data: toArtist(r.data) }));

const fetchArtists = async (ids: string[]) => {
  const responses = await Promise.all(
    ids.map((id) => axios.get<ArtistOut>(`/artists/${encodeURIComponent(id)}`))
  );
  return { ...responses[0], data: { artists: responses.map((r) => toArtist(r.data)) } };
};

const fetchArtistAlbums = async (
  id: string,
  params: { limit?: number; offset?: number; include_groups?: string; market?: string } = {}
) => {
  const { data } = await axios.get<Album[]>(`/artists/${encodeURIComponent(id)}/albums`);
  const items = (
    data as unknown as { artist?: string | null; title?: string | null; year?: number | null; cover_url?: string | null }[]
  ).map((a) => toAlbum({ artist: id, ...a }));
  const page = toPage(items, items.length, params.limit ?? items.length, params.offset ?? 0);
  return { data: page as unknown as Pagination<Album> };
};

const fetchArtistTopTracks = async (id: string) => {
  const { data } = await axios.get<TrackOut[]>(`/artists/${encodeURIComponent(id)}/top`);
  return { data: { tracks: data.map(toTrack) } };
};

/** Similar/related no existe en nuestra API; la radio usa /recommend/radio. */
const fetchSimilarArtists = async (_id: string) => {
  return { data: { artists: [] as Artist[] } };
};

export const artistService = {
  fetchArtist,
  fetchArtists,
  fetchArtistAlbums,
  fetchArtistTopTracks,
  fetchSimilarArtists,
};
