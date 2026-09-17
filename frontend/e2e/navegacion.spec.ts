import { test, expect } from '@playwright/test';
import { obtenerToken, entrar, cazarErrores, RUTAS, API } from './utils';

test.describe('Navegación', () => {
  let token: string;
  test.beforeAll(async ({ request }) => { token = await obtenerToken(request); });

  for (const [nombre, ruta] of RUTAS) {
    test(`${nombre} carga sin fallos de API ni errores de JS`, async ({ page }) => {
      const errores = cazarErrores(page);
      const fallos: string[] = [];
      page.on('response', (r) => {
        // las imágenes que falten no cuentan: dependen del catálogo local
        if (r.url().startsWith(API) && r.status() >= 400 && !r.url().includes('/media/')) {
          fallos.push(`${r.status()} ${r.url().replace(API, '')}`);
        }
      });

      await entrar(page, token);
      await page.goto(ruta);
      await page.waitForTimeout(3500);

      const dom = await page.evaluate(() => document.getElementById('root')?.innerHTML.length ?? 0);
      expect(dom, `${nombre} apenas pintó nada`).toBeGreaterThan(3000);
      expect(fallos, `${nombre} tuvo peticiones fallidas`).toEqual([]);
      expect(errores, `${nombre} lanzó errores de JS`).toEqual([]);
    });
  }

  test('ninguna petición sale hacia Spotify', async ({ page }) => {
    const externas: string[] = [];
    page.on('request', (r) => {
      if (/spotify|scdn\.co|bootstrapcdn/.test(r.url())) externas.push(r.url());
    });
    await entrar(page, token);
    await page.goto('/search/bad%20bunny');
    await page.waitForTimeout(3000);
    expect(externas).toEqual([]);
  });

  test('una ruta inexistente no rompe la aplicación', async ({ page }) => {
    const errores = cazarErrores(page);
    await entrar(page, token);
    await page.goto('/esta-ruta-no-existe');
    await page.waitForTimeout(2000);
    expect(errores).toEqual([]);
  });
});
