/** Lo que devuelve la API de RadioPV (ver docs/02_API.md). */

export interface TrackOut {
  id: number;
  title: string;
  artist: string;
  album?: string | null;
  year?: number | null;
  era?: string | null;
  genre?: string | null;
  language?: string | null;
  bpm?: number | null;
  energy?: number | null;
  tags?: string | null;
  is_remix: boolean;
  explicit: boolean;
  duration?: number | null;            // segundos
  cover?: string | null;               // "/media/covers/693008911.jpg"
  feat?: string | null;
  rank?: number | null;
  gain_db?: number | null;
}

export interface ArtistOut {
  id: number;
  name: string;
  image?: string | null;
  nb_fan?: number | null;
  track_count?: number | null;
}

export interface PlaylistOut {
  id: number;
  name: string;
  description?: string | null;
  type: string;
  n_tracks: number;
  /** Dueno de la lista. Nulo en las que genera la aplicacion para todos. */
  user_id?: number | null;
  /** URL de la portada propia de la lista (/media/covers/...), o nulo si no tiene. */
  cover?: string | null;
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface MeOut {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  created_at?: string | null;
}

export interface Facets {
  genres: FacetValue[];
  eras: FacetValue[];
  languages: FacetValue[];
  years: FacetValue[];
  moods: FacetValue[];
}
