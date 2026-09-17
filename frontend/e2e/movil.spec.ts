import { test, expect } from '@playwright/test';
import { obtenerToken, entrar, RUTAS } from './utils';

/** En móvil nada puede salirse de la pantalla: es el defecto más visible de una app así. */
test.describe('Móvil', () => {
  let token: string;
  test.beforeAll(async ({ request }) => { token = await obtenerToken(request); });

  for (const [nombre, ruta] of RUTAS) {
    test(`${nombre} no desborda a lo ancho`, async ({ page }) => {
      await entrar(page, token);
      await page.goto(ruta);
      await page.waitForTimeout(3000);
      const { scroll, cliente } = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        cliente: document.documentElement.clientWidth,
      }));
      // 2 px de tolerancia por redondeos de escala
      expect(scroll, `${nombre} se sale ${scroll - cliente}px a la derecha`).toBeLessThanOrEqual(cliente + 2);
    });
  }
});
