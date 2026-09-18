import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';

// Interfaz
import axios from '../../axios';
import { toTrack, toPlaylist } from '../../api/adapt';

// Interfaces
import type { Pagination } from '../../interfaces/api';
import type { Track } from '../../interfaces/track';
import type { Category } from '../../interfaces/categories';
import type { Playlist } from '../../interfaces/playlists';
import type { PlaylistOut, TrackOut } from '../../api/types';

const PLACEHOLDER = '/images/playlist.png';

/** id = `{tipo}:{valor}` (p. ej. `genre:Reggaeton`, `era:2020s`). Devuelve el param y el valor. */
const parseId = (id: string): { param: string; value: string } => {
  const i = id.indexOf(':');
  return i === -1 ? { param: 'genre', value: id } : { param: id.slice(0, i), value: id.slice(i + 1) };
};

/**
 * Las listas que la aplicación genera PARA ESE GÉNERO (`Top pop`, `Top bachata`…).
 *
 * La página de género enseñaba sólo una rejilla de canciones sueltas. Como la música se escucha
 * en listas, primero van las listas del género (que la aplicación ya crea) y las canciones
 * después. Si no hay ninguna lista para ese facet (las eras y los estados de ánimo no tienen
 * «Top …»), la sección simplemente no aparece: mejor nada que un hueco vacío.
 *
 * Se compara en minúsculas y sin acentos, porque el nombre de la lista y el valor del facet no
 * siempre se escriben igual.
 */
const sinAcentos = (s: string) =>
  s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

const listasDelGenero = async (param: string, value: string): Promise<Playlist[]> => {
  if (param !== 'genre') return [];
  const { data } = await axios.get<PlaylistOut[]>('/playlists/system');
  const objetivo = `top ${sinAcentos(value)}`;
  return data
    .filter((p) => sinAcentos(p.name) === objetivo)
    .sort((a, b) => (b.n_tracks ?? 0) - (a.n_tracks ?? 0))
    .map((p) => toPlaylist(p) as unknown as Playlist);
};

const initialState: {
  category: Category | null;
  playlists: Track[];
  listas: Playlist[];
  loading: boolean;
  total: number;
} = {
  category: null,
  playlists: [],
  listas: [],
  loading: true,
  total: 0,
};

/** RadioPV: /genre/:id lista canciones por facet (género/era/mood/idioma), paginado por
 *  X-Total-Count. El estado `playlists` se reutiliza pero ahora lleva Track[] (GridItemList los
 *  pinta como TrackCard). */
export const fetchGenre = createAsyncThunk<[Category, Track[], number, Playlist[]], string>(
  'genre/fetchGenre',
  async (id) => {
    const { param, value } = parseId(id);
    const r = await axios.get<TrackOut[]>('/tracks', { params: { [param]: value, limit: 50 } });
    const total = Number(r.headers['x-total-count'] ?? r.data.length) || r.data.length;
    const category: Category = {
      id, name: value, href: '',
      icons: [{ url: PLACEHOLDER, width: 300, height: 300 }],
      count: total,
    };
    // Las listas del género se piden en paralelo y no pueden tumbar la página: si fallan, la
    // rejilla de canciones se sigue viendo.
    const listas = await listasDelGenero(param, value).catch(() => [] as Playlist[]);
    return [category, r.data.map(toTrack), total, listas];
  }
);

/** Paginación (A8): carga el siguiente tramo de canciones del facet y lo añade a la lista. */
export const fetchMoreGenre = createAsyncThunk<[Track[], number], { id: string; offset: number }>(
  'genre/fetchMoreGenre',
  async ({ id, offset }) => {
    const { param, value } = parseId(id);
    const r = await axios.get<TrackOut[]>('/tracks', { params: { [param]: value, limit: 50, offset } });
    const total = Number(r.headers['x-total-count'] ?? r.data.length) || r.data.length;
    return [r.data.map(toTrack), total];
  }
);

const genreSlice = createSlice({
  name: 'genre',
  initialState,
  reducers: {
    setGenre: (state, action) => {
      state.category = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder.addCase(fetchGenre.pending, (state) => {
      state.loading = true;
    });
    builder.addCase(fetchGenre.fulfilled, (state, action) => {
      state.category = action.payload[0];
      state.playlists = action.payload[1];
      state.total = action.payload[2];
      state.listas = action.payload[3];
      state.loading = false;
    });
    builder.addCase(fetchMoreGenre.fulfilled, (state, action) => {
      state.playlists = [...state.playlists, ...action.payload[0]];
      state.total = action.payload[1];
    });
  },
});

export const genreActions = {
  fetchGenre,
  fetchMoreGenre,
  ...genreSlice.actions,
};

export default genreSlice.reducer;
