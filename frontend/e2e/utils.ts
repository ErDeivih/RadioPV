import { Page, APIRequestContext, expect } from '@playwright/test';

export const API = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
export const USUARIO = { email: 'e2e@ejemplo.com', password: 'clave-larga-e2e', nombre: 'E2E' };

/** Registra (o entra si ya existe) y devuelve el token de sesión. */
export async function obtenerToken(request: APIRequestContext): Promise<string> {
  const reg = await request.post(`${API}/auth/register`, { data: { ...USUARIO, display_name: USUARIO.nombre } });
  if (reg.ok()) return (await reg.json()).access_token;
  const login = await request.post(`${API}/auth/login`, {
    form: { username: USUARIO.email, password: USUARIO.password },
  });
  expect(login.ok(), `login falló: ${login.status()} ${await login.text()}`).toBeTruthy();
  return (await login.json()).access_token;
}

/** Deja la sesión iniciada en el navegador antes de cargar la app. */
export async function entrar(page: Page, token: string) {
  await page.goto('/');
  await page.evaluate((t) => localStorage.setItem('access_token', t), token);
  await page.goto('/');
  await page.waitForTimeout(1500);
}

/** Recoge SOLO los errores reales de JavaScript.
 *  Se descartan los `Event` pelados: los emiten los <img> que no cargan (una carátula que falta)
 *  a través de promesas rechazadas, y no son fallos de la aplicación. */
export function cazarErrores(page: Page): string[] {
  const errores: string[] = [];
  page.on('pageerror', (e) => {
    const texto = String(e);
    const esRecurso = texto === 'Event' || texto === '[object Event]' || /^Event\b/.test(texto);
    if (!esRecurso) errores.push(texto);
  });
  return errores;
}

export const RUTAS: Array<[string, string]> = [
  ['Portada', '/'],
  ['Explorar', '/search'],
  ['Búsqueda', '/search/bad%20bunny'],
  ['Género', '/genre/reggaeton'],
  ['Artista', '/artist/Bad%20Bunny'],
  ['Guardadas', '/collection/tracks'],
  ['Ajustes', '/settings'],
];
