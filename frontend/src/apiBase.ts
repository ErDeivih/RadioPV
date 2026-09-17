/**
 * URL base de la API.
 *
 * En producción la web se sirve por el mismo origen y nginx proxya `/api/` al contenedor
 * de la API (ver `deploy/nginx.conf`). Por eso el valor por defecto es **relativo**: así la
 * app funciona desde cualquier máquina —el PC, el móvil por Tailscale, la IP de la LAN—
 * sin recompilar nada y **sin CORS**, porque navegador y API comparten origen.
 *
 * Antes esto era `import.meta.env.VITE_API_URL` a secas, y como `frontend/.env` no viaja al
 * repositorio, el build de producción quedó con `http://127.0.0.1:8000` dentro: el navegador
 * llamaba a la propia máquina del usuario y **todo fallaba en silencio** (el login incluido).
 *
 * Para desarrollo se puede seguir apuntando a otro sitio con `VITE_API_URL` en `frontend/.env`.
 *
 * El build de producción lo hace el SERVIDOR, dentro de un contenedor (ver
 * frontend/Dockerfile). No hace falta Node en la máquina del servidor ni copiar el build a
 * mano: basta con `git push`, y el autodespliegue reconstruye la imagen de la web.
 */
export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) || '/api';
