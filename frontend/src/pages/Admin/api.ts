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

/** Recuentos de los atajos de limpieza. Cada uno es exactamente lo que selecciona su atajo. */
export interface Salud {
  sin_fichero: { n: number };
  no_descargadas: { n: number };
  perdidas: { n: number };
  cuarentena: { n: number };
  fallidas: { n: number };
  incompletas: { n: number };
  pendientes: { n: number };
  rank_bajo_40: { n: number };
  rank_bajo_60: { n: number };
  cortas: { n: number };
  sin_idioma: { n: number };
  /** Canciones con intro detectada (voz/diálogo antes de la música). */
  con_intro: { n: number };
  /** Canciones con cola detectada (voz/despedida después de la música). */
  con_cola: { n: number };
  /** Cuántas se han mirado ya (el PC las revisa por lotes en cada vuelta). */
  extremos_revisados: { n: number };
  /** Cuántas se han cambiado por otra versión sin esa intro. */
  version_limpia: { n: number };
}

export interface Facets {
  languages: FacetItem[];
  genres: FacetItem[];
  artists: FacetItem[];
  years: FacetItem[];
  status: FacetItem[];
  sources: FacetItem[];
  eras: FacetItem[];
  booleanos: {
    explicit: { n: number };
    remixes: { n: number };
    huerfanas: { n: number };
    total: { n: number };
  };
  salud: Salud;
}

/** Los campos de pista que devuelve la tabla de gestión (incluye los de los filtros nuevos). */
export interface TrackRowExtra {
  explicit?: number | null;
  is_remix?: number | null;
  era?: string | null;
  rank?: number | null;
  match_score?: number | null;
  /** Segundos de intro detectada (voz/diálogo antes de que empiece la música). */
  intro_seg?: number | null;
  /** Segundos de cola detectada (voz/despedida después de la música). */
  cola_seg?: number | null;
  /** 1 si se encontró y se puso otra versión de la misma canción sin intro. */
  version_limpia?: number | null;
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
  // --- filtros adicionales (los mismos que acepta el borrado en masa) ---
  title?: string;
  tags?: string;
  era?: string;
  explicit?: boolean;
  is_remix?: boolean;
  has_file_path?: boolean;
  rank_min?: number;
  rank_max?: number;
  duration_min?: number;
  duration_max?: number;
  bpm_min?: number;
  bpm_max?: number;
  energy_min?: number;
  energy_max?: number;
  match_score_min?: number;
  // --- extremos: intros/colas que no son la canción ---
  intro_min?: number;
  cola_min?: number;
  con_extremos?: number;
  added_from?: string;
  added_to?: string;
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

/** Resultado de borrar canciones por su id (la tabla, con selección). */
export interface BorradoResult {
  borradas: number;
  solicitadas: number;
  vetadas: boolean;
  /** Ficheros que NO se han podido borrar del disco (permisos, disco lleno, fichero en uso). */
  ficheros_no_borrados?: number;
  detalle_fallos?: string[];
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
    axios
      .post<BorradoResult>('/admin/tracks/delete', { ids, veto })
      .then((r) => r.data),

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
