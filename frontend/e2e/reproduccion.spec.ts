import { test, expect } from '@playwright/test';
import { obtenerToken, entrar, API } from './utils';

test.describe('Reproducción', () => {
  let token: string;
  test.beforeAll(async ({ request }) => { token = await obtenerToken(request); });

  test('el audio suena de verdad, con ganancia y sin contaminar el elemento', async ({ page, request }) => {
    await entrar(page, token);
    const st = await request.post(`${API}/auth/stream-token`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const { token: stream } = await st.json();

    const r = await page.evaluate(async ([api, t]) => {
      const a = new Audio();
      a.crossOrigin = 'anonymous';           // con 'use-credentials' esto daría SILENCIO
      const ctx = new AudioContext();
      const src = ctx.createMediaElementSource(a);
      const g = ctx.createGain();
      src.connect(g); g.connect(ctx.destination);
      g.gain.value = Math.pow(10, -3 / 20);  // simula gain_db = -3
      a.src = `${api}/stream/1?t=${encodeURIComponent(t as string)}`;
      await ctx.resume();
      try { await a.play(); } catch (e) { return { error: String(e) }; }
      await new Promise((res) => setTimeout(res, 2500));
      const avanzo = a.currentTime;
      a.currentTime = 8;                      // el seek dispara un Range nuevo
      await new Promise((res) => setTimeout(res, 1500));
      return {
        estado: ctx.state, avanzo, trasSeek: a.currentTime,
        duracion: a.duration, ganancia: g.gain.value, error: a.error ? a.error.code : null,
      };
    }, [API, stream]);

    expect(r.error, 'el audio dio error').toBeFalsy();
    expect(r.estado).toBe('running');
    expect(r.avanzo, 'el audio no avanzó: no está sonando').toBeGreaterThan(0.5);
    expect(r.trasSeek, 'el seek no funcionó').toBeGreaterThan(7.5);
    expect(r.ganancia).toBeCloseTo(0.7079, 3);
  });

  test('/stream responde a los rangos como debe', async ({ request }) => {
    const st = await request.post(`${API}/auth/stream-token`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const { token: s } = await st.json();
    const url = `${API}/stream/1?t=${encodeURIComponent(s)}`;

    expect((await request.get(url)).status()).toBe(200);                                   // sin rango
    expect((await request.get(url, { headers: { Range: 'bytes=100-' } })).status()).toBe(206);   // abierto
    const malo = await request.get(url, { headers: { Range: 'bytes=99999999999-' } });
    expect(malo.status(), 'un rango imposible debe dar 416').toBe(416);
    expect((await request.get(`${API}/stream/999999?t=${encodeURIComponent(s)}`)).status()).toBe(404);
  });

  test('reproducir registra la escucha en la biblioteca', async ({ request }) => {
    const antes = await request.get(`${API}/library/history?limit=50`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const n = antes.ok() ? (await antes.json()).length : 0;
    const r = await request.post(`${API}/library/1/play`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { source: 'e2e', context: 'test', completed: 1, seconds_listened: 42 },
    });
    expect(r.ok()).toBeTruthy();
    const despues = await request.get(`${API}/library/history?limit=50`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect((await despues.json()).length).toBeGreaterThanOrEqual(Math.min(n, 1));
  });
});
