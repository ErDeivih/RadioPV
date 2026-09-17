import { getToken, clearToken } from '../../api/token';
import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';

// Utils
import axios from '../../axios';
import { getFromLocalStorageWithExpiry } from '../../utils/localstorage';

// Services / API nuestra
import { authService } from '../../services/auth';
import * as apiAuth from '../../api/auth';
import { uiActions } from './ui';

// Interfaces
import type { User } from '../../interfaces/user';

const initialState: { token?: string; playerLoaded: boolean; user?: User; requesting: boolean } = {
  user: undefined,
  requesting: true,
  playerLoaded: false,
  token: getToken() || undefined,
};

/** Compañero de compatibilidad: ya no redirige a Spotify. Si hay token pide el usuario. */
export const loginToSpotify = createAsyncThunk<{ token?: string; loaded: boolean }>(
  'auth/loginToSpotify',
  async (_, thunkAPI) => {
    const userToken: string | undefined = getToken() as string;
    if (userToken) {
      axios.defaults.headers.common['Authorization'] = 'Bearer ' + userToken;
      thunkAPI.dispatch(fetchUser());
      return { token: userToken, loaded: false };
    }
    return { token: undefined, loaded: true };
  }
);

/** Login con credenciales contra nuestra API (POST /auth/login, formulario). */
export const loginWithCredentials = createAsyncThunk<
  { token?: string; loaded: boolean },
  { email: string; password: string }
>('auth/loginWithCredentials', async ({ email, password }, thunkAPI) => {
  const data = await apiAuth.login(email, password);
  axios.defaults.headers.common['Authorization'] = 'Bearer ' + data.access_token;
  thunkAPI.dispatch(fetchUser());
  return { token: data.access_token, loaded: false };
});

export const fetchUser = createAsyncThunk('auth/fetchUser', async (_, { dispatch }) => {
  try {
    const response = await authService.fetchUser();
    return response.data;
  } catch (e) {
    // A1 · sesión caducada (401 en /auth/me): limpiar la sesión y pedir acceso, no dejar la
    // pantalla muerta. El interceptor de axios ya borró el token; aquí abrimos el modal.
    clearToken();
    try { delete axios.defaults.headers.common['Authorization']; } catch { /* ignore */ }
    dispatch(uiActions.openLoginModal(''));
    throw e;
  }
});

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setRequesting(state, action: { payload: { requesting: boolean } }) {
      state.requesting = action.payload.requesting;
    },
    setToken(state, action: { payload: { token?: string } }) {
      state.token = action.payload.token;
    },
    setPlayerLoaded(state, action: { payload: { playerLoaded: boolean } }) {
      state.playerLoaded = action.payload.playerLoaded;
    },
  },
  extraReducers: (builder) => {
    builder.addCase(loginToSpotify.fulfilled, (state, action) => {
      state.token = action.payload.token;
      state.requesting = !action.payload.loaded;
    });
    builder.addCase(loginWithCredentials.fulfilled, (state, action) => {
      state.token = action.payload.token;
      state.requesting = !action.payload.loaded;
    });
    builder.addCase(fetchUser.fulfilled, (state, action) => {
      state.user = action.payload;
      state.requesting = false;
    });
    builder.addCase(fetchUser.rejected, (state) => {
      // A1 · sesión caducada: sin sesión ni petición pendiente; la UI muestra el login.
      state.user = undefined;
      state.requesting = false;
    });
  },
});

export const authActions = { ...authSlice.actions, loginToSpotify, loginWithCredentials, fetchUser };

export default authSlice.reducer;
