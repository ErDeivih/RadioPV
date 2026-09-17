#!/usr/bin/env bash
# deploy.sh — despliega o actualiza RadioPV en el servidor.
#
#   ./deploy.sh              actualiza el codigo y reinicia lo que haga falta
#   ./deploy.sh --build-web  ademas reconstruye el frontend (necesita node)
#   ./deploy.sh --first      primera instalacion (crea .env si no existe)
#
# Pensado para ejecutarse desde /opt/stacks/radiopv dentro del servidor.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

AZUL='\033[1;34m'; VERDE='\033[1;32m'; ROJO='\033[1;31m'; FIN='\033[0m'
paso() { echo -e "${AZUL}==> $*${FIN}"; }
ok()   { echo -e "${VERDE}  OK  $*${FIN}"; }
err()  { echo -e "${ROJO}  !!  $*${FIN}" >&2; }

BUILD_WEB=0
PRIMERA=0
for arg in "$@"; do
  case "$arg" in
    --build-web) BUILD_WEB=1 ;;
    --first)     PRIMERA=1 ;;
  esac
done

# ---------------------------------------------------------------- 1. .env
paso "Comprobando el fichero .env"
if [ ! -f .env ]; then
  if [ "$PRIMERA" -eq 1 ]; then
    CLAVE="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
    IP="$(hostname -I | awk '{print $1}')"
    cat > .env <<EOF
# Generado por deploy.sh el $(date '+%Y-%m-%d %H:%M')
RADIOPV_SECRET_KEY=$CLAVE
RADIOPV_ALLOWED_ORIGINS=http://servidor.local:8090,http://$IP:8090,http://servidor.local:8000
EOF
    chmod 600 .env
    ok ".env creado con una SECRET_KEY nueva"
  else
    err "Falta .env. Ejecuta primero:  ./deploy.sh --first"
    exit 1
  fi
else
  ok ".env presente"
fi

# ---------------------------------------------------------------- 2. git pull
if [ -d .git ]; then
  paso "Actualizando el codigo desde Git"
  git fetch --prune
  ANTES="$(git rev-parse HEAD)"
  git pull --ff-only
  DESPUES="$(git rev-parse HEAD)"
  if [ "$ANTES" = "$DESPUES" ]; then
    ok "ya estaba al dia ($(git rev-parse --short HEAD))"
  else
    ok "actualizado $ANTES -> $DESPUES"
    git --no-pager log --oneline "$ANTES..$DESPUES" | head -20
  fi
else
  paso "Sin repositorio Git: se despliega el codigo tal cual esta"
fi

# ---------------------------------------------------------------- 3. frontend
if [ "$BUILD_WEB" -eq 1 ]; then
  paso "Construyendo el frontend"
  if command -v node >/dev/null 2>&1; then
    ( cd frontend && yarn install --immutable && yarn build )
    ok "frontend/dist generado"
  else
    err "Node no esta instalado; usa el dist que venga en el repo o compila en tu PC"
  fi
fi

# ---------------------------------------------------------------- 4. permisos
paso "Asegurando la carpeta de datos"
mkdir -p data
if [ -d /srv/data/media/music ]; then
  ok "/srv/data/media/music presente"
else
  err "Falta /srv/data/media/music (el recolector descarga ahi)"
fi

# ---------------------------------------------------------------- 5. arranque
paso "Reconstruyendo y levantando los contenedores"
docker compose pull --ignore-buildable || true
docker compose build
docker compose up -d --remove-orphans
docker compose ps

# ---------------------------------------------------------------- 6. salud
paso "Esperando a la API"
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    ok "la API responde:"
    curl -fsS http://127.0.0.1:8000/health
    echo
    exit 0
  fi
  sleep 2
done

err "La API no responde tras 60s. Revisa:  docker compose logs api --tail 50"
exit 1
