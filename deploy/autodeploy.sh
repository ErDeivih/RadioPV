#!/usr/bin/env bash
# autodeploy.sh — comprueba si hay commits nuevos en GitHub y, si los hay, despliega.
#
# Pensado para lanzarlo el timer `radiopv-autodeploy.timer` cada pocos minutos.
# Si no hay cambios, sale en silencio sin tocar nada.
#
#   Instalar:  ver docs/DESPLIEGUE_SERVIDOR.md §7
#   Ver log:   journalctl -u radiopv-autodeploy -n 80 --no-pager
set -euo pipefail

DIR="/opt/stacks/radiopv"
cd "$DIR"

echo "--- $(date '+%F %T') comprobando GitHub ---"

# 1) ¿Hay algo nuevo?
if ! git fetch --quiet origin main; then
  echo "ERROR: no se pudo consultar GitHub (¿red?). Se reintentará en la próxima pasada."
  exit 1
fi

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "sin cambios ($(git rev-parse --short HEAD))"
  exit 0
fi

echo ">>> CAMBIOS DETECTADOS: $LOCAL -> $REMOTE"
git --no-pager log --oneline "$LOCAL..$REMOTE" || true

CAMBIOS="$(git diff --name-only "$LOCAL" "$REMOTE")"

# 2) ¿Qué tipo de cambio es? Para reconstruir solo lo necesario.
RECONSTRUIR=0
WEB=0
if echo "$CAMBIOS" | grep -qE '^(backend/|radiov/|scripts/|run_|Dockerfile|requirements)'; then
  RECONSTRUIR=1
fi
if echo "$CAMBIOS" | grep -q '^frontend/'; then
  WEB=1
fi

# 3) Bajar el código
git pull --ff-only

# 4) Reconstruir la imagen si tocó Python
if [ "$RECONSTRUIR" = "1" ]; then
  echo "--- reconstruyendo la imagen (backend/recolector) ---"
  docker compose build
fi

docker compose up -d --remove-orphans

# 5) Reconstruir el frontend si tocó, y si hay Node
if [ "$WEB" = "1" ]; then
  if command -v node >/dev/null 2>&1; then
    echo "--- reconstruyendo el frontend ---"
    ( cd frontend && yarn install --immutable && yarn build )
  else
    echo "AVISO: cambiaron ficheros de frontend/ pero no hay Node instalado."
    echo "       Compílalo en tu PC y copia frontend/build"
  fi
fi

echo ">>> DESPLEGADO $(git rev-parse --short HEAD)"
