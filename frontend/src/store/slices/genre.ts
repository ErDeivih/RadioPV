import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';

// Interfaz
import axios from '../../axios';
import { toTrack } from '../../api/adapt';

// Interfaces
import type { Pagination } from '../../interfaces/api';
import type { Track } from '../../interfaces/track';
import type { Category } from '../../interfaces/categories';
import type { TrackOut } from '../../api/types';

const PLACEHOLDER = '/images/playlist.png';

/** id = `{tipo}:{valor}` (p. ej. `genre:Reggaeton`, `era:2020s`). Devuelve el param y el valor. */
const parseId = (id: string): { param: string; value: string } => {
  const i = id.indexOf(':');
  return i === -1 ? { param: 'genre', value: id } : { param: id.slice(0, i), value: id.slice(i + 1) };
};

const initialState: {
  category: Category | null;
  playlists: Track[];
  loading: boolean;
  total: number;
} = {
  category: null,
  playlists: [],
  loading: true,
  total: 0,
};

/** RadioPV: /genre/:id lista canciones por facet (género/era/mood/idioma), paginado por
 *  X-Total-Count. El estado `playlists` se reutiliza pero ahora lleva Track[] (GridItemList los
 *  pinta como TrackCard). */
export const fetchGenre = createAsyncThunk<[Category, Track[], number], string>(
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
    return [category, r.data.map(toTrack), total];
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
