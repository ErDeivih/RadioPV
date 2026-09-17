import { defineConfig, devices } from '@playwright/test';

/** Pruebas de extremo a extremo de RadioNano.
 *  Requiere el backend en marcha (VITE_API_URL) y sirve el build con fallback de SPA. */
const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  // Si el entorno no puede descargar los navegadores de Playwright, se le indica dónde está
  // un Chromium ya instalado:  E2E_CHROMIUM=/ruta/al/chrome  (en un equipo normal no hace falta).
  use: {
    baseURL: BASE,
    ...(process.env.E2E_CHROMIUM
      ? { launchOptions: { executablePath: process.env.E2E_CHROMIUM } }
      : {}),
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'escritorio', use: { ...devices['Desktop Chrome'] } },
    { name: 'movil', use: { ...devices['Pixel 5'] }, testMatch: /movil\.spec\.ts/ },
  ],
});
