import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';

// Interfaz
import axios from '../../axios';

// Interfaces
import type { Category } from '../../interfaces/categories';

const PLACEHOLDER = '/images/playlist.png';

const facetToCategory = (prefix: string, value: string, count: number): Category => ({
  id: `${prefix}:${value}`,
  name: value,
  href: '',
  icons: [{ url: PLACEHOLDER, width: 300, height: 300 }],
  count,
});

const initialState: {
  loading: boolean;
  categories: Category[];
} = {
  loading: true,
  categories: [],
};

/** RadioPV: Browse usa los facets reales del catálogo (géneros, eras, moods, idiomas), no las
 *  categorías de Spotify (que ya no existen). Cada una enlaza a /genre/{tipo}:{valor}. */
export const fetchCategories = createAsyncThunk('browse/fetchCategories', async () => {
  const { data } = await axios.get<{
    genres: { value: string; count: number }[];
    eras: { value: string; count: number }[];
    languages: { value: string; count: number }[];
    moods: { value: string; count: number }[];
  }>('/facets');
  const categories: Category[] = [];
  const push = (prefix: string, arr: { value: string; count: number }[]) => {
    for (const f of arr) categories.push(facetToCategory(prefix, f.value, f.count));
  };
  push('genre', data.genres);
  push('era', data.eras);
  push('language', data.languages);
  push('mood', data.moods);
  return categories;
});

const browseSlice = createSlice({
  name: 'browse',
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder.addCase(fetchCategories.fulfilled, (state, action) => {
      state.loading = false;
      state.categories = action.payload;
    });
  },
});

export const browseActions = {
  ...browseSlice.actions,
  fetchCategories,
};

export default browseSlice.reducer;
