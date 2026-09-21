import { createAsyncThunk, createSlice, PayloadAction } from '@reduxjs/toolkit';

// Interfaces

import type { PlaylistItem } from '../../interfaces/playlists';

// Constants
import { userService } from '../../services/users';
import { RootState } from '../store';

const initialState: {
  total: number;
  items: PlaylistItem[];
  // `loading` existe para poder distinguir «todavía no ha llegado la lista» de «no hay ninguna
  // canción guardada»: sin esto, la página de «Me gusta» de un usuario sin favoritos se quedaba en
  // blanco, sin lista y sin decir nada, y parecía rota.
  loading: boolean;
} = {
  total: 0,
  items: [],
  loading: true,
};

export const fetchLikeSongs = createAsyncThunk<[PlaylistItem[], number]>(
  'likedSongs/fetchLikeSongs',
  async () => {
    const response = await userService.getSavedTracks({ limit: 50 });
    return [response.data.items, response.data.total];
  }
);

export const fetchMore = createAsyncThunk<PlaylistItem[]>(
  'likedSongs/fetchMore',
  async (_, api) => {
    const {
      likedSongs: { items },
    } = api.getState() as RootState;
    const response = await userService.getSavedTracks({ limit: 50, offset: items.length });
    return response.data.items;
  }
);

const likedSongsSlice = createSlice({
  name: 'likedSongs',
  initialState,
  reducers: {
    removeSong: (state, action: PayloadAction<{ id: string }>) => {
      state.items = state.items.filter((item) => item.track.id !== action.payload.id);
      state.total -= 1;
    },
  },
  extraReducers: (builder) => {
    builder.addCase(fetchLikeSongs.pending, (state) => {
      state.loading = true;
    });
    builder.addCase(fetchLikeSongs.fulfilled, (state, action) => {
      state.items = action.payload[0];
      state.total = action.payload[1];
      state.loading = false;
    });
    // Si la petición falla también se quita el «cargando»: si no, la página se quedaba en blanco
    // para siempre, que es peor que decir que no se ha podido cargar.
    builder.addCase(fetchLikeSongs.rejected, (state) => {
      state.loading = false;
    });
    builder.addCase(fetchMore.fulfilled, (state, action) => {
      state.items.push(...action.payload);
    });
  },
});

export const likedSongsActions = {
  ...likedSongsSlice.actions,
  fetchLikeSongs,
  fetchMore,
};

export default likedSongsSlice.reducer;
