import axios from '../axios';

import type { Track } from '../interfaces/track';
import type { Playlist, PlaylistItem } from '../interfaces/playlists';
import type { Pagination, PaginationQueryParams } from '../interfaces/api';
import { toPlaylist, toTrack, toPage } from '../api/adapt';
import type { PlaylistOut, TrackOut } from '../api/types';

const tidFromUri = (uri: string) => {
  const parts = String(uri).split(':');
  return parts[parts.length - 1];
};

const getPlaylist = async (playlistId: string) => {
  const { data } = await axios.get<PlaylistOut>(`/playlists/${playlistId}`);
  return { data: toPlaylist(data, undefined) as unknown as Playlist };
};

const getPlaylistItems = async (
  playlistId: string,
  params: PaginationQueryParams = { limit: 50 }
) => {
  const { data } = await axios.get<TrackOut[]>(`/playlists/${playlistId}/tracks`);
  const items = data.map((t) => ({
    added_at: '', added_by: { id: 'me', display_name: 'RadioPV' },
    is_local: false, primary_color: '', track: toTrack(t),
  }));
  const page = toPage(items, items.length, params.limit ?? items.length, params.offset ?? 0);
  return { data: page as unknown as Pagination<PlaylistItem> };
};

const getMyPlaylists = async (params: PaginationQueryParams = {}) => {
  const { data } = await axios.get<PlaylistOut[]>('/playlists');
  const items = data.map((p) => toPlaylist(p));
  const page = toPage(items, items.length, params.limit ?? items.length, params.offset ?? 0);
  return { data: page as unknown as Pagination<Playlist> };
};

const getPlaylists = async (_userId: string, params: PaginationQueryParams = {}) => getMyPlaylists(params);

const getFeaturedPlaylists = async (_params: { locale?: string; limit?: number } = {}) => {
  const empty = { items: [], total: 0, limit: 0, offset: 0, next: null, previous: null } as unknown as Pagination<Playlist>;
  return { data: { playlists: empty } };
};

const createPlaylist = async (
  _userId: string,
  data: { name: string; description?: string; public?: boolean; collaborative?: boolean }
) => {
  const { data: created } = await axios.post<PlaylistOut>('/playlists', { name: data.name, description: data.description ?? '' });
  return { data: toPlaylist(created) };
};

const addPlaylistItems = async (playlistId: string, uris: string[], _snapshot: string) => {
  await Promise.all(uris.map((u) => axios.post(`/playlists/${playlistId}/tracks/${tidFromUri(u)}`)));
  return { data: true };
};

const removePlaylistItems = async (playlistId: string, uris: string[], _snapshot: string) => {
  await Promise.all(uris.map((u) => axios.delete(`/playlists/${playlistId}/tracks/${tidFromUri(u)}`)));
  return { data: true };
};

const reorderPlaylistItems = async (playlistId: string, uris: string[], _start: number, _before: number, _len: number, _snapshot: string) => {
  await axios.put(`/playlists/${playlistId}/order`, uris.map(tidFromUri));
  return { data: true };
};

const changePlaylistDetails = async (playlistId: string, data: { name?: string; description?: string; public?: boolean; collaborative?: boolean; type?: string }) => {
  await axios.patch(`/playlists/${playlistId}`, { name: data.name, description: data.description });
  return { data: true };
};

/** Borra la playlist (y sus playlist_tracks). Solo el propietario. */
const deletePlaylist = async (playlistId: string) => {
  await axios.delete(`/playlists/${playlistId}`);
  return { data: true };
};

const changePlaylistImage = async (_id: string, _image: string, _content: string) => ({ data: true });

const getRecommendations = async (params: { seed_artists?: string; seed_genres?: string; seed_tracks?: string; limit?: number }) => {
  const { data } = await axios.get<TrackOut[]>('/recommend', { params: { n: params.limit ?? 25 } });
  return { data: { tracks: data.map(toTrack) } };
};

export const playlistService = {
  getPlaylist,
  getPlaylists,
  getMyPlaylists,
  createPlaylist,
  deletePlaylist,
  getPlaylistItems,
  addPlaylistItems,
  getRecommendations,
  changePlaylistImage,
  removePlaylistItems,
  getFeaturedPlaylists,
  reorderPlaylistItems,
  changePlaylistDetails,
};
