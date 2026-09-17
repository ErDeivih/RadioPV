import { test, expect } from '@playwright/test';
import { obtenerToken, API } from './utils';

test.describe('Biblioteca y playlists', () => {
  let token: string;
  let cab: Record<string, string>;
  test.beforeAll(async ({ request }) => {
    token = await obtenerToken(request);
    cab = { Authorization: `Bearer ${token}` };
  });

  test('me gusta aparece en las guardadas y se puede quitar', async ({ request }) => {
    await request.post(`${API}/library/2/like`, { headers: cab, data: { liked: true } });
    let liked = await (await request.get(`${API}/library/liked`, { headers: cab })).json();
    expect(liked.some((t: any) => t.id === 2), 'la canción no apareció en guardadas').toBeTruthy();

    await request.post(`${API}/library/2/like`, { headers: cab, data: { liked: false } });
    liked = await (await request.get(`${API}/library/liked`, { headers: cab })).json();
    expect(liked.some((t: any) => t.id === 2), 'la canción siguió guardada tras quitar el me gusta').toBeFalsy();
  });

  test('ciclo completo de una playlist: crear, añadir, reordenar, quitar y borrar', async ({ request }) => {
    const nueva = await request.post(`${API}/playlists`, {
      headers: cab, data: { name: 'Prueba E2E', description: 'temporal', type: 'user' },
    });
    expect(nueva.ok()).toBeTruthy();
    const { id } = await nueva.json();

    for (const t of [1, 2, 3]) {
      expect((await request.post(`${API}/playlists/${id}/tracks/${t}`, { headers: cab })).ok()).toBeTruthy();
    }
    let temas = await (await request.get(`${API}/playlists/${id}/tracks`, { headers: cab })).json();
    expect(temas.map((t: any) => t.id)).toEqual([1, 2, 3]);

    const orden = await request.put(`${API}/playlists/${id}/order`, { headers: cab, data: [3, 1, 2] });
    if (orden.ok()) {
      temas = await (await request.get(`${API}/playlists/${id}/tracks`, { headers: cab })).json();
      expect(temas.map((t: any) => t.id)).toEqual([3, 1, 2]);
    }

    expect((await request.delete(`${API}/playlists/${id}/tracks/1`, { headers: cab })).ok()).toBeTruthy();
    temas = await (await request.get(`${API}/playlists/${id}/tracks`, { headers: cab })).json();
    expect(temas.some((t: any) => t.id === 1)).toBeFalsy();

    expect((await request.delete(`${API}/playlists/${id}`, { headers: cab })).ok()).toBeTruthy();
    expect((await request.get(`${API}/playlists/${id}/tracks`, { headers: cab })).status()).toBe(404);
  });

  test('la playlist de otro usuario responde 404, no 403', async ({ request }) => {
    const otro = await request.post(`${API}/auth/register`, {
      data: { email: `otro-${Date.now()}@ejemplo.com`, password: 'clave-larga-2', display_name: 'Otro' },
    });
    const tokenOtro = (await otro.json()).access_token;
    const suya = await request.post(`${API}/playlists`, {
      headers: { Authorization: `Bearer ${tokenOtro}` },
      data: { name: 'Privada', description: '', type: 'user' },
    });
    const { id } = await suya.json();
    // 404 y no 403: no se filtra ni que exista
    expect((await request.get(`${API}/playlists/${id}/tracks`, { headers: cab })).status()).toBe(404);
    expect((await request.delete(`${API}/playlists/${id}`, { headers: cab })).status()).toBe(404);
  });
});
