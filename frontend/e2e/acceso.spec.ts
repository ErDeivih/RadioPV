import { test, expect } from '@playwright/test';
import { obtenerToken, entrar, API } from './utils';

test.describe('Acceso', () => {
  test('la sesión sobrevive a recargar la página', async ({ page, request }) => {
    const token = await obtenerToken(request);
    await entrar(page, token);
    await page.reload();
    await page.waitForTimeout(2500);
    const guardado = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(guardado).toBe(token);
    const dom = await page.evaluate(() => document.getElementById('root')?.innerHTML.length ?? 0);
    expect(dom).toBeGreaterThan(3000);
  });

  test('REGRESIÓN A1 · con la sesión caducada NO se queda en blanco', async ({ page }) => {
    // Un token con formato válido pero firmado con otra clave: el backend responde 401.
    const falso =
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
      'eyJzdWIiOiI5OTk5OSIsInZlciI6MCwic2NvcGUiOiJhY2Nlc3MiLCJleHAiOjE3MDAwMDAwMDB9.' +
      'firma-invalida-a-proposito';
    await page.goto('/');
    await page.evaluate((t) => localStorage.setItem('access_token', t), falso);
    await page.goto('/');
    await page.waitForTimeout(4000);

    const dom = await page.evaluate(() => document.getElementById('root')?.innerHTML.length ?? 0);
    expect(dom, 'la app se quedó en blanco con la sesión caducada (fallo A1)').toBeGreaterThan(2000);

    const texto = (await page.evaluate(() => document.body.innerText)).toLowerCase();
    expect(
      /inicia sesión|iniciar sesión|registrarse|acceder/.test(texto),
      'con la sesión caducada debería ofrecerse el acceso',
    ).toBeTruthy();
  });

  test('el token de streaming se pide y sirve para /stream', async ({ request }) => {
    const token = await obtenerToken(request);
    const st = await request.post(`${API}/auth/stream-token`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(st.ok()).toBeTruthy();
    const { token: stream, expires_in } = await st.json();
    expect(expires_in).toBeGreaterThan(60);

    const r = await request.get(`${API}/stream/1?t=${encodeURIComponent(stream)}`, {
      headers: { Range: 'bytes=0-1023' },
    });
    expect(r.status()).toBe(206);
    expect(r.headers()['content-range']).toMatch(/^bytes 0-1023\/\d+$/);
  });

  test('el token de sesión NO vale para /stream (ámbitos separados)', async ({ request }) => {
    const token = await obtenerToken(request);
    const r = await request.get(`${API}/stream/1?t=${encodeURIComponent(token)}`);
    expect(r.status()).toBe(401);
  });
});
