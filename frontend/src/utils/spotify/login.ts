import Axios from 'axios';
import { getFromLocalStorageWithExpiry, setLocalStorageWithExpiry } from '../localstorage';
import axios from 'axios';

/* eslint-disable import/no-anonymous-default-export */
const client_id = import.meta.env.VITE_SPOTIFY_CLIENT_ID;
const redirect_uri = import.meta.env.VITE_SPOTIFY_REDIRECT_URL;

const authUrl = new URL('https://accounts.spotify.com/authorize');

const SCOPES = [
  'ugc-image-upload',

  // Web Playback SDK: `streaming` only yields a playable device when the account-info
  // scopes are also granted. Without these two the SDK registers a device that Spotify
  // rejects as "Device not found" on playback. They are required, not optional.
  'streaming',
  'user-read-email',
  'user-read-private',

  'user-read-playback-state',
  'user-modify-playback-state',
  'user-read-currently-playing',

  'playlist-read-private',
  'playlist-modify-public',
  'playlist-modify-private',
  'playlist-read-collaborative',

  'user-follow-modify',
  'user-follow-read',

  'user-read-playback-position',
  'user-top-read',
  'user-read-recently-played',

  'user-library-read',
  'user-library-modify',
] as const;

const sha256 = async (plain: string) => {
  const encoder = new TextEncoder();
  const data = encoder.encode(plain);
  return window.crypto.subtle.digest('SHA-256', data);
};

const base64encode = (input: ArrayBuffer) => {
  // @ts-ignore
  return btoa(String.fromCharCode(...new Uint8Array(input)))
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
};

const generateRandomString = (length: number) => {
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const values = crypto.getRandomValues(new Uint8Array(length));
  return values.reduce((acc, x) => acc + possible[x % possible.length], '');
};

const logInWithSpotify = async () => {
  // Always mint a fresh verifier so the challenge sent to /authorize and the
  // verifier sent to /api/token are guaranteed to be the same pair.
  const codeVerifier = generateRandomString(64);
  localStorage.setItem('code_verifier', codeVerifier);

  const hashed = await sha256(codeVerifier);
  const codeChallenge = base64encode(hashed);

  authUrl.search = new URLSearchParams({
    client_id,
    redirect_uri,
    response_type: 'code',
    scope: SCOPES.join(' '),
    code_challenge_method: 'S256',
    code_challenge: codeChallenge,
  }).toString();

  window.location.href = authUrl.toString();
};

// An authorization code is single-use. React StrictMode mounts effects twice in
// dev, which would exchange the same code twice (the second fails with
// "Invalid authorization code"). Share one in-flight exchange per code.
const inFlightExchanges: Record<string, Promise<string> | undefined> = {};

const requestToken = async (code: string) => {
  const existing = inFlightExchanges[code];
  if (existing) return existing;

  const exchange = (async () => {
    const code_verifier = localStorage.getItem('code_verifier') as string;

    const body = {
      code,
      client_id,
      redirect_uri,
      code_verifier,
      grant_type: 'authorization_code',
    };

    const { data: response } = await Axios.post<{
      access_token: string;
      token_type: string;
      expires_in: number;
      refresh_token: string;
    }>('https://accounts.spotify.com/api/token', body, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    if (response.access_token) {
      setLocalStorageWithExpiry(
        'access_token',
        response.access_token,
        response.expires_in * 60 * 60
      );
      axios.defaults.headers.common['Authorization'] = 'Bearer ' + response.access_token;
      localStorage.setItem('refresh_token', response.refresh_token);
      // Verifier is spent once the code is exchanged; clear it so a future login
      // generates a fresh challenge/verifier pair.
      localStorage.removeItem('code_verifier');
    }

    return response.access_token;
  })();

  inFlightExchanges[code] = exchange;
  return exchange;
};

const getToken = async () => {
  const token = getFromLocalStorageWithExpiry('access_token');
  if (token) return [token, true];

  const urlParams = new URLSearchParams(window.location.search);

  let code = urlParams.get('code') as string;
  if (code) {
    // Strip ?code from the URL immediately so a reload can't re-exchange a
    // spent authorization code.
    window.history.replaceState({}, document.title, window.location.pathname);
    return [await requestToken(code), true];
  }

  return [null, false];
};

export const getRefreshToken = async () => {
  // RadioPV: la sesión usa nuestro JWT (scope=access), no el OAuth de Spotify. No hay refresh
  // token de Spotify ni llamada a accounts.spotify.com. Devolvemos null (sin token).
  return null;
};

export default { logInWithSpotify, getToken, getRefreshToken };
