import { getToken, setToken, clearToken } from './token';
import Axios from 'axios';

/** Autenticación con nuestra API (sustituye al OAuth de Spotify).
 *  /auth/login usa OAuth2PasswordRequestForm (formulario); /auth/register es JSON. */
const API = import.meta.env.VITE_API_URL as string;
const raw = Axios.create({ baseURL: API });

const auth = () => ({ Authorization: `Bearer ${getToken()}` });

export const login = async (email: string, password: string) => {
  const form = new URLSearchParams({ username: email, password });
  const { data } = await raw.post('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  setToken(data.access_token);
  return data;                                    // { access_token, token_type, user }
};

export const register = (email: string, password: string, displayName: string, invite?: string) =>
  raw
    .post('/auth/register', {
      email,
      password,
      display_name: displayName,
      invite_code: invite,
    })
    .then((r) => {
      setToken(r.data.access_token);
      return r.data;
    });

export const logout = async () => {
  try {
    await raw.post('/auth/logout', {}, { headers: auth() });
  } finally {
    clearToken();
    localStorage.removeItem('stream_token');
  }
};

export const me = async () => {
  const { data } = await raw.get('/auth/me', { headers: auth() });
  return data;
};
