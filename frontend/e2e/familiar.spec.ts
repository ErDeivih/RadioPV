import { test, expect } from '@playwright/test';
import { obtenerToken, API } from './utils';

/** Perfil familiar: con el filtro puesto no puede colarse NINGUNA canción explícita. */
test.describe('Filtro de contenido explícito', () => {
  let token: string;
  let cab: Record<string, string>;
  test.beforeAll(async ({ request }) => {
    token = await obtenerToken(request);
    cab = { Authorization: `Bearer ${token}` };
  });

  test('el catálogo tiene canciones explícitas (si no, la prueba no valdría)', async ({ request }) => {
    const todas = await (await request.get(`${API}/tracks?limit=200`)).json();
    expect(todas.filter((t: any) => t.explicit).length,
      'sin explícitas en el catálogo esta prueba no demuestra nada').toBeGreaterThan(0);
  });

  const listas = [
    ['catálogo', '/tracks?limit=100&explicit=false'],
    ['recomendadas', '/recommend?n=50&explicit=false'],
    ['mix diario', '/recommend/daily?n=50&explicit=false'],
    ['radio', '/recommend/radio?seed_track=1&n=50&explicit=false'],
    ['guardadas', '/library/liked?explicit=false'],
  ];

  for (const [nombre, ruta] of listas) {
    test(`${nombre}: ninguna explícita con el filtro`, async ({ request }) => {
      const r = await request.get(`${API}${ruta}`, { headers: cab });
      if (r.status() === 404) test.skip(true, `${ruta} no existe`);
      expect(r.ok(), `${ruta} devolvió ${r.status()}`).toBeTruthy();
      const datos = await r.json();
      const lista = Array.isArray(datos) ? datos : (datos.items ?? []);
      const coladas = lista.filter((t: any) => t.explicit === true);
      expect(coladas.map((t: any) => `${t.artist} - ${t.title}`),
        `se colaron explícitas en ${nombre}`).toEqual([]);
    });
  }
});
