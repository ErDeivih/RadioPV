#!/usr/bin/env bash
# autodeploy-todos — recorre los proyectos de /opt/stacks y despliega los que tengan
# commits nuevos en GitHub.
#
# NO es específico de RadioPV: sirve para CUALQUIER proyecto que cumpla dos condiciones:
#   1. estar en /opt/stacks/<nombre>/ y ser un repositorio git
#   2. tener rama remota de seguimiento (origin/<rama>)
#
# Para cada uno:
#   · git fetch  → si no hay commits nuevos, no hace nada y sigue con el siguiente
#   · si los hay → git pull y, según lo que cambiara:
#        - backend/, radiov/, Dockerfile, requirements*, .dockerignore → reconstruye la imagen
#        - frontend/                                                   → reconstruye la web,
#          que COMPILA el frontend dentro del contenedor (no hace falta Node en la máquina)
#        - docker-compose.yml presente                                 → docker compose up -d
#
# Uso:
#   autodeploy-todos                 revisa /opt/stacks
#   autodeploy-todos /otra/ruta      revisa otra carpeta
#
# Log:  journalctl -u autodeploy-todos -n 100 --no-pager
#
# ────────────────────────────────────────────────────────────────────────────────────────────────
# ESTE FICHERO VIVE EN DOS SITIOS Y TIENEN QUE COINCIDIR:
#   · el servidor:  /usr/local/bin/autodeploy-todos
#   · el repositorio: deploy/autodeploy-todos.sh   ← esta copia
# Se guarda aquí para que no se pierda (el servidor no está en git) y para poder revisarlo.
# Para instalarlo, después de un `git push`:
#   docker run --rm -v /opt/stacks/radiopv:/repo -v /usr/local/bin:/dest alpine \
#     sh -c 'cp /repo/deploy/autodeploy-todos.sh /dest/autodeploy-todos && chmod 755 /dest/autodeploy-todos'
#
# POR QUÉ SE AVISA (18/09/2026)
# ----------------------------
# Antes, un fallo al compilar la web se tragaba con un `|| echo "AVISO: ..."` y el script
# terminaba diciendo «OK -> <commit>». O sea: una hoja de estilos rota hacía que el despliegue
# **pareciera** correcto mientras el servidor seguía sirviendo la interfaz VIEJA. Costó 20
# minutos de confusión: se daba por desplegado un cambio que no estaba, y las pruebas contra el
# servidor fallaban sin motivo aparente. Ahora un fallo de compilación:
#   · se marca como FALLO (no como OK),
#   · enseña las últimas líneas del error en el registro,
#   · manda un aviso al móvil por ntfy,
#   · y el script termina con código distinto de cero (lo ve `systemctl status`).
# ────────────────────────────────────────────────────────────────────────────────────────────────
set -uo pipefail

BASE="${1:-/opt/stacks}"
NTFY="${NTFY_URL:-http://127.0.0.1:8085/alertas-servidor}"

avisar() {   # avisar <titulo> <mensaje> [prioridad]
  curl -fsS -m 10 \
    -H "Title: $1" \
    -H "Priority: ${3:-default}" \
    -H "Tags: warning" \
    -d "$2" "$NTFY" >/dev/null 2>&1 || true
}

echo "════════════ $(date '+%F %T') · revisando $BASE ════════════"

repos=0
actualizados=0
fallos=0

for DIR in "$BASE"/*/; do
  [ -d "${DIR}.git" ] || continue
  repos=$((repos + 1))
  NOMBRE="$(basename "$DIR")"
  echo ""
  echo "──── $NOMBRE ────"

  RESULTADO="$(
    cd "$DIR" || exit 0

    # ¿Se puede consultar el remoto?
    if ! git fetch --quiet origin 2>/dev/null; then
      echo "ERROR: no se pudo consultar el remoto (¿red?)"
      exit 0
    fi

    RAMA="$(git rev-parse --abbrev-ref HEAD)"
    LOCAL="$(git rev-parse HEAD)"
    REMOTE="$(git rev-parse "origin/$RAMA" 2>/dev/null || true)"

    if [ -z "$REMOTE" ]; then
      echo "sin rama remota de seguimiento; se omite"
      exit 0
    fi

    if [ "$LOCAL" = "$REMOTE" ]; then
      echo "sin cambios ($(git rev-parse --short HEAD))"
      exit 0
    fi

    echo "CAMBIOS: $(git rev-parse --short "$LOCAL") -> $(git rev-parse --short "$REMOTE")"
    git --no-pager log --oneline "$LOCAL..$REMOTE" | sed 's/^/   /'

    CAMBIOS="$(git diff --name-only "$LOCAL" "$REMOTE")"

    RECONSTRUIR=0
    WEB=0
    if echo "$CAMBIOS" | grep -qE '^(backend/|radiov/|scripts/|run_|Dockerfile|requirements|\.dockerignore)'; then
      RECONSTRUIR=1
    fi
    # El frontend tambien se reconstruye con docker (ver mas abajo): no hace falta Node en
    # la maquina, porque se compila dentro de un contenedor.
    if echo "$CAMBIOS" | grep -qE '^frontend/'; then
      WEB=1
    fi

    if ! git pull --ff-only; then
      echo "ERROR: git pull fallo (¿cambios locales?). Revisalo a mano."
      echo "__FALLO__ $NOMBRE pull:git pull fallo"
      echo "__CAMBIOS__"
      exit 0
    fi

    # Desplegar con docker compose si el proyecto lo tiene
    if [ -f docker-compose.yml ] || [ -f docker-compose.yaml ] || [ -f compose.yaml ]; then
      FALLOS=""
      DETALLE=""

      if [ "$RECONSTRUIR" = "1" ]; then
        echo "reconstruyendo la imagen del backend..."
        if ! docker compose build api worker collector >/tmp/autodeploy-backend.log 2>&1; then
          if ! docker compose build >/tmp/autodeploy-backend.log 2>&1; then
            FALLOS="$FALLOS backend"
            echo "FALLO: no se pudo construir la imagen del backend. Ultimas lineas:"
            tail -n 20 /tmp/autodeploy-backend.log | sed 's/^/    /'
            DETALLE="$(tail -n 4 /tmp/autodeploy-backend.log | tr '\n' ' ')"
          fi
        fi
      fi

      if [ "$WEB" = "1" ]; then
        # El frontend se COMPILA dentro de la imagen (frontend/Dockerfile): asi no hace
        # falta Node en el servidor. Antes esto solo avisaba de que no habia node y la
        # interfaz se quedaba vieja sin que nadie se enterara; y despues el fallo se tragaba
        # con un "AVISO" y el script decia OK igualmente.
        echo "reconstruyendo la imagen de la web (compila el frontend)..."
        if ! docker compose build web >/tmp/autodeploy-web.log 2>&1; then
          FALLOS="$FALLOS web"
          echo "FALLO: no se pudo compilar la web. La interfaz que se sirve es la ANTERIOR."
          echo "Ultimas lineas del error:"
          tail -n 20 /tmp/autodeploy-web.log | sed 's/^/    /'
          DETALLE="$(tail -n 4 /tmp/autodeploy-web.log | tr '\n' ' ')"
        fi
      fi

      # Los contenedores se levantan igual: asi el backend nuevo entra aunque la web falle. Lo
      # que NO se hace es decir que todo ha ido bien.
      if ! docker compose up -d --remove-orphans >/tmp/autodeploy-up.log 2>&1; then
        FALLOS="$FALLOS up"
        echo "FALLO: docker compose up. Ultimas lineas:"
        tail -n 15 /tmp/autodeploy-up.log | sed 's/^/    /'
        DETALLE="$(tail -n 4 /tmp/autodeploy-up.log | tr '\n' ' ')"
      else
        echo "contenedores actualizados"
      fi

      if [ -n "$FALLOS" ]; then
        echo "RESULTADO: DESPLIEGUE A MEDIAS -> fallos en:$FALLOS"
        echo "__FALLO__ $NOMBRE fallos en:$FALLOS · $DETALLE"
      else
        echo "OK -> $(git rev-parse --short HEAD)"
      fi
    else
      echo "(sin docker-compose: solo se ha bajado el codigo)"
      echo "OK -> $(git rev-parse --short HEAD)"
    fi

    echo "__CAMBIOS__"
    exit 0
  )"

  echo "$RESULTADO" | sed '/^__CAMBIOS__$/d' | sed '/^__FALLO__/d' | sed 's/^/  /'

  case "$RESULTADO" in
    *"__CAMBIOS__"*) actualizados=$((actualizados + 1)) ;;
  esac
  if echo "$RESULTADO" | grep -q '^__FALLO__'; then
    fallos=$((fallos + 1))
    MENSAJE="$(echo "$RESULTADO" | grep '^__FALLO__' | sed 's/^__FALLO__ //')"
    avisar "Despliegue a medias: $NOMBRE" "El despliegue de $NOMBRE NO se ha completado.
$MENSAJE

Mira el registro en el servidor:
  journalctl -u autodeploy-todos -n 100 --no-pager" "high"
  fi
done

echo ""
echo "════════════ fin · repos revisados: $repos · actualizados: $actualizados · a medias: $fallos ════════════"

# Código de salida != 0 si algo quedó a medias: así `systemctl status` y el vigilante lo ven.
[ "$fallos" -eq 0 ]
