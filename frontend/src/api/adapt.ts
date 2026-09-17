import type { TrackOut, ArtistOut, PlaylistOut, MeOut } from './types';
import type { User } from '../interfaces/user';
import type { Artist, SimpleArtist } from '../interfaces/artist';
import type { Album } from '../interfaces/albums';
import type { Track } from '../interfaces/track';
import { API_BASE } from '../apiBase';

/** Traduce nuestro TrackOut/ArtistOut a la forma "estilo Spotify" que la UI ya espera. */
const API = API_BASE;
const img = (p?: string | null) => (p ? API + p : undefined);
const PLACEHOLDER = '/images/playlist.png';   // ya existe en public/images

const _album_images = (url?: string) => [{ url: url ?? PLACEHOLDER, width: 640, height: 640 }];

const _artist_simple = (name: string): SimpleArtist => ({
  id: name, name, type: 'artist', href: '', uri: `radiopv:artist:${name}`,
  external_urls: { spotify: '' },
});

/** Nuestro /auth/me → User (spotify-shape) que el slice de auth espera. */
export const toUser = (u: MeOut): User => ({
  id: String(u.id),
  display_name: u.display_name ?? '',
  email: u.email,
  uri: `radiopv:user:${u.id}`,
  type: 'user' as const,
  images: [{ url: '', height: 0, width: 0 }, { url: '', height: 0, width: 0 }],
  followers: { href: null, total: 0 },
  external_urls: { spotify: '' },
  explicit_content: { filter_enabled: false, filter_locked: false },
});

export const toArtist = (a: ArtistOut) => ({
  id: a.name,                     // en RadioPV un artista se identifica por NOMBRE (para /artists/{name})
  name: a.name,
  type: 'artist' as const,
  uri: `radiopv:artist:${a.name}`,
  href: '',
  images: a.image ? [{ url: img(a.image)!, height: 640, width: 640 }] : [],
  followers: { href: '', total: a.nb_fan ?? 0 },
  genres: [],
  popularity: Math.min(100, Math.round(((a.track_count ?? 0) / 100) * 100)),
  external_urls: { spotify: '' },
});

export const toTrack = (t: TrackOut) => ({
  id: String(t.id),
  name: t.title,
  duration_ms: Math.round((t.duration ?? 0) * 1000),
  explicit: t.explicit,
  track_number: 1,
  disc_number: 1,
  is_local: false as const,
  is_playable: true,
  popularity: Math.round(((t.rank ?? 0) / 1_000_000) * 100),
  uri: `radiopv:track:${t.id}`,
  type: 'track' as const,
  href: '',
  preview_url: '',
  external_urls: { spotify: '' },
  external_ids: { isrc: '' },
  available_markets: [],
  artists: [_artist_simple(t.artist)],
  album: {
    id: `${t.artist}::${t.album ?? ''}`,
    name: t.album ?? '',
    album_type: 'album' as const,
    release_date: t.year ? String(t.year) : '',
    release_date_precision: 'year' as const,
    images: _album_images(img(t.cover)),   // cover ya es "/media/covers/x"; img lo hace absoluta
    artists: [_artist_simple(t.artist)],
    uri: `radiopv:album:${t.artist}::${t.album ?? ''}`,
    type: 'album' as const,
    href: '',
    external_urls: { spotify: '' },
    available_markets: [],
    total_tracks: 0,
  },
  // extras propios: la UI de Spotify los ignora, los nuestros los usan
  radiopv: {
    bpm: t.bpm,
    energy: t.energy,
    era: t.era,
    genre: t.genre,
    tags: t.tags,
    feat: t.feat,
    gain_db: t.gain_db ?? 0,
  },
});

export const toPlaylist = (p: PlaylistOut, cover?: string) => ({
  id: String(p.id),
  name: p.name,
  description: p.description ?? '',
  type: 'playlist' as const,
  uri: `radiopv:playlist:${p.id}`,
  href: '',
  images: [{ url: cover ?? PLACEHOLDER, height: 640, width: 640 }],
  tracks: { href: '', total: p.n_tracks },
  followers: { href: '', total: 0 },
  owner: { id: 'me', display_name: 'RadioPV' },
  public: false,
  collaborative: false,
  snapshot_id: '',
  external_urls: { spotify: '' },
});

/** Convierte un TrackOut a un PlaylistItem (como espera la UI de la biblioteca "me gusta"). */
export const toPlaylistItem = (t: TrackOut) => ({
  added_at: '',
  added_by: { id: 'me', display_name: 'RadioPV', type: 'user' },
  is_local: false,
  primary_color: '',
  track: toTrack(t),
});

/** AlbumOut (de /artists/{name}/albums) → Album (spotify-shape). El id lleva la clave `artista::álbum`. */
export const toAlbum = (a: { artist?: string | null; title?: string | null; year?: number | null; cover_url?: string | null }) => {
  const key = `${a.artist ?? ''}::${a.title ?? ''}`;
  return {
    id: key,
    name: a.title ?? '',
    album_type: 'album' as const,
    artists: a.artist ? [_artist_simple(a.artist)] : [],
    available_markets: [],
    external_urls: { spotify: '' },
    href: '',
    images: _album_images(img(a.cover_url)),
    release_date: a.year ? String(a.year) : '',
    release_date_precision: 'year' as const,
    total_tracks: 0,
    type: 'album' as const,
    uri: `radiopv:album:${key}`,
  };
};

/** Envoltorio de paginación que la UI espera (items/total/next). */
export const toPage = <T,>(items: T[], total: number, limit: number, offset: number) => ({
  items,
  total,
  limit,
  offset,
  next: offset + limit < total ? String(offset + limit) : null,
  previous: offset > 0 ? String(Math.max(0, offset - limit)) : null,
  href: '',
});
