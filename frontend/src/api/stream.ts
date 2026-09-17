import { getToken, setToken, clearToken } from './token';
/** Token de reproducción (ámbito `stream`, 30 min) y URL de /stream.
 *  El <audio> no puede enviar la cabecera Authorization → el token viaja en la URL.
 *  Como el token queda incrustado en `audio.src`, hay que poder INVALIDARLO y recargar:
 *  si caduca mientras la canción está pausada, el siguiente seek pediría un rango con el
 *  token viejo → 401 → la reproducción muere en silencio. Ver `recargarSrc` en playerController. */
const API = import.meta.env.VITE_API_URL as string;

let token: string | null = null;
let expira = 0;

export const streamToken = async (): Promise<string> => {
  if (token && Date.now() < expira - 60_000) return token;
  const r = await fetch(`${API}/auth/stream-token`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!r.ok) throw new Error('No se pudo obtener el token de reproducción');
  const d = await r.json();
  token = d.token;
  expira = Date.now() + d.expires_in * 1000;
  return token!;
};

/** Fuerza que la próxima llamada pida un token nuevo (tras un 401 o al cerrar sesión). */
export const invalidarStreamToken = () => { token = null; expira = 0; };

/** Pedir el token por adelantado (al entrar). Así `streamUrl` no hace red dentro del clic:
 *  un `await` de red antes de `play()` rompe la cadena del gesto del usuario en Safari/iOS. */
export const precalentarStreamToken = () => { void streamToken().catch(() => undefined); };

export const streamUrl = async (trackId: number | string) =>
  `${API}/stream/${trackId}?t=${encodeURIComponent(await streamToken())}`;
