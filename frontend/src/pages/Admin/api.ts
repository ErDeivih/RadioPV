import axios from '../../axios';

/** Cliente de la API de administración (`/admin`). Requiere usuario con `is_admin`. */

export interface IngestStatus {
  enabled: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface AdminStatus {
  tracks_total: number;
  tracks_por_estado: { status: string | null; n: number }[];
  biblioteca_gb: number;
  vetados: number;
  disco: { total_gb: number; libre_gb: number; usado_pct: number } | null;
  rutas: { base_music: string; catalog_dir: string; download_dir: string };
  ingesta: IngestStatus;
}

export interface TrackRow {
  id: number;
  title: string;
  artist: string;
  album: string | null;
  year: number | null;
  genre: string | null;
  language: string | null;
  bpm: number | null;
  energy: number | null;
  duration: number | null;
  file_size: number | null;
  status: string | null;
  source: string | null;
  added_at: string | null;
  file_path: string | null;
}

export interface FacetItem {
  valor: string;
  n: number;
}

export interface Facets {
  languages: FacetItem[];
  genres: FacetItem[];
  artists: FacetItem[];
  years: FacetItem[];
  status: FacetItem[];
  sources: FacetItem[];
}

export interface TrackListResponse {
  total: number;
  limit: number;
  offset: number;
  items: TrackRow[];
}

export interface TrackFilters {
  q?: string;
  artist?: string;
  album?: string;
  genre?: string;
  language?: string;
  status?: string;
  year_min?: number;
  year_max?: number;
  sort?: string;
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

/** Filtros que entiende el borrado en masa (mismo subconjunto que /admin/tracks)
 *  más las **listas**, que permiten operar sobre muchos elementos elegidos a la vez. */
export type BulkFilter = Omit<TrackFilters, 'sort' | 'order' | 'limit' | 'offset'> & {
  ids?: number[];
  artists?: string[];
  albums?: string[];
  genres?: string[];
  languages?: string[];
  years?: number[];
};

/** Una fila de la vista agrupada (por artista, álbum, género, idioma o año). */
export interface GroupRow {
  valor: string | number | null;
  n: number;
  size: number;
  languages: string | null;
  genres: string | null;
  year_min: number | null;
  year_max: number | null;
}

export interface GroupResponse {
  by: string;
  total_grupos: number;
  limit: number;
  offset: number;
  items: GroupRow[];
}

export type GroupBy = 'artist' | 'album' | 'genre' | 'language' | 'year' | 'status' | 'source';

export interface BlacklistEntry {
  id: number;
  kind: 'artist' | 'song';
  value: string;
  reason: string | null;
  active: number;
  created_at: string | null;
}

export interface BulkResult {
  afectadas: number;
  borradas: number;
  vetadas: number;
  dry_run: boolean;
}

export interface EventRow {
  id: number;
  ts: string | null;
  level: string | null;
  message: string;
}

export const adminApi = {
  status: () => axios.get<AdminStatus>('/admin/status').then((r) => r.data),

  events: (limit = 100) =>
    axios.get<EventRow[]>('/admin/events', { params: { limit } }).then((r) => r.data),

  tracks: (f: TrackFilters) =>
    axios.get<TrackListResponse>('/admin/tracks', { params: f }).then((r) => r.data),

  /** Biblioteca agrupada (por artista, álbum, género, idioma o año) con recuentos. */
  group: (params: {
    by: GroupBy;
    q?: string;
    artist?: string;
    genre?: string;
    language?: string;
    status?: string;
    year_min?: number;
    year_max?: number;
    min_tracks?: number;
    sort?: 'n' | 'size' | 'valor';
    order?: 'asc' | 'desc';
    limit?: number;
    offset?: number;
  }) => axios.get<GroupResponse>('/admin/group', { params }).then((r) => r.data),

  facets: () => axios.get<Facets>('/admin/facets').then((r) => r.data),

  deleteTracks: (ids: number[], veto: boolean) =>
    axios.post('/admin/tracks/delete', { ids, veto }).then((r) => r.data),

  blacklistTracks: (ids: number[]) =>
    axios.post('/admin/tracks/blacklist', { ids }).then((r) => r.data),

  vetoArtist: (name: string, deleteTracks = true) =>
    axios
      .post('/admin/artists/veto', { name, delete_tracks: deleteTracks })
      .then((r) => r.data),

  bulkVetoArtists: (names: string[], dryRun = false) =>
    axios.post('/admin/artists/bulk-veto', { names, dry_run: dryRun }).then((r) => r.data),

  purge: () => axios.post('/admin/purge').then((r) => r.data),

  blacklist: (kind?: 'artist' | 'song') =>
    axios
      .get<BlacklistEntry[]>('/admin/blacklist', { params: kind ? { kind } : {} })
      .then((r) => r.data),

  addBlacklist: (kind: 'artist' | 'song', value: string, reason = '') =>
    axios.post('/admin/blacklist', { kind, value, reason }).then((r) => r.data),

  removeBlacklist: (id: number) =>
    axios.delete(`/admin/blacklist/${id}`).then((r) => r.data),

  ingest: () => axios.get<IngestStatus>('/admin/ingest').then((r) => r.data),

  setIngest: (enabled: boolean) =>
    axios.put<IngestStatus>('/admin/ingest', { enabled }).then((r) => r.data),

  /** Operación en masa por filtros (sin mandar IDs). */
  bulk: (
    filters: BulkFilter,
    action: 'delete' | 'blacklist' = 'delete',
    veto = true,
    dryRun = false,
    limit = 0
  ) =>
    axios
      .post<BulkResult>('/admin/tracks/bulk', {
        filters,
        action,
        veto,
        dry_run: dryRun,
        limit,
      })
      .then((r) => r.data),
};

/** Etiquetas legibles para los idiomas que usa el recolector. */
export const LANGUAGE_LABELS: Record<string, string> = {
  es: 'Español',
  en: 'Inglés',
  it: 'Italiano',
  fr: 'Francés',
  pt: 'Portugués',
  other: 'Otro / sin detectar',
};

/** Etiquetas legibles para los géneros. */
export const GENRE_LABELS: Record<string, string> = {
  reggaeton: 'Reggaetón',
  pop: 'Pop',
  rock: 'Rock',
  bachata: 'Bachata',
  salsa: 'Salsa',
  merengue: 'Merengue',
  latin: 'Latino / Urbano',
  dance: 'Dance / Electrónica',
  rap: 'Rap / Hip-Hop',
  ballad: 'Balada',
  cumbia: 'Cumbia',
  corridos: 'Corridos / Mexicano',
  flamenco: 'Flamenco',
  reggae: 'Reggae',
  disco: 'Disco / Funk',
  classical: 'Clásica',
  house: 'House',
  electro: 'Electrónica',
  instrumental: 'Instrumental',
  soundtrack: 'Banda sonora',
  jazz: 'Jazz',
  blues: 'Blues',
  metal: 'Metal',
  indie: 'Indie',
  folk: 'Folk',
  techno: 'Techno',
  lofibeat: 'Lo-Fi',
  gospel: 'Gospel',
  banda: 'Banda',
  soul: 'Soul / R&B',
  other: 'Variado',
};

export const STATUS_LABELS: Record<string, string> = {
  pendiente: 'Pendiente',
  descargando: 'Descargando',
  descargada: 'Descargada',
  fallida: 'Fallida',
  en_cola: 'En cola',
  cuarentena: 'Cuarentena',
};

export const labelLang = (v?: string | null) => (v ? LANGUAGE_LABELS[v] ?? v : '—');
export const labelGenre = (v?: string | null) => (v ? GENRE_LABELS[v] ?? v : '—');
export const labelStatus = (v?: string | null) => (v ? STATUS_LABELS[v] ?? v : '—');

export const mb = (bytes?: number | null) =>
  bytes ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : '—';

export const duracion = (seg?: number | null) => {
  if (!seg) return '—';
  const m = Math.floor(seg / 60);
  const s = Math.round(seg % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
};
