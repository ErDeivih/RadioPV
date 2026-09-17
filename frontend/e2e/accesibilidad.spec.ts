import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { obtenerToken, entrar, RUTAS } from './utils';

/** Sin violaciones graves o críticas de accesibilidad en ninguna pantalla. */
test.describe('Accesibilidad', () => {
  let token: string;
  test.beforeAll(async ({ request }) => { token = await obtenerToken(request); });

  for (const [nombre, ruta] of RUTAS) {
    test(`${nombre} sin violaciones serias`, async ({ page }) => {
      await entrar(page, token);
      await page.goto(ruta);
      await page.waitForTimeout(3000);
      const { violations } = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa'])
        .analyze();
      const graves = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
      expect(
        graves.map((v) => `${v.impact}: ${v.id} (${v.nodes.length}) — ${v.help}`),
        `${nombre} tiene problemas graves de accesibilidad`,
      ).toEqual([]);
    });
  }
});
