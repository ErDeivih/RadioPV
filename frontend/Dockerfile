# RadioPV · web (build de React servido por nginx)
#
# POR QUÉ EXISTE ESTE FICHERO
# --------------------------
# El frontend hay que compilarlo, y el servidor no tiene Node. Antes se compilaba en el PC
# y se copiaba el resultado a mano, así que el autodespliegue bajaba los cambios del
# frontend pero NO los aplicaba: solo dejaba un aviso en el log y la interfaz se quedaba
# vieja. Con esto, el servidor compila el frontend dentro de un contenedor y no hace falta
# Node en la máquina.
#
# EL CONTEXTO DE CONSTRUCCIÓN ES LA RAÍZ DEL REPOSITORIO (no frontend/), a propósito: así
# puede copiar también deploy/nginx.conf, que es la configuración con el proxy /api y el
# resolver del DNS de Docker. Por eso las rutas llevan el prefijo frontend/.
#
#   docker build -f frontend/Dockerfile -t radiopv-web .
#
# Ojo: hace falta el .dockerignore de la raíz. Sin él, cada build enviaría al demonio los
# 1,29 GB de carátulas de data/ y los 0,58 GB de node_modules.

# ---------------------------------------------------------------- 1. compilar
FROM node:22-alpine AS builder
WORKDIR /app

# Yarn 4 (el yarn.lock es formato Berry). corepack lo instala desde el campo
# "packageManager" de package.json; el yarn que trae node:22-alpine es el 1.x y NO sabe
# leer un lockfile Berry.
RUN corepack enable

# Primero solo el manifiesto y la configuración: mientras no cambien, esta capa se reutiliza
# y no hay que reinstalar las dependencias en cada cambio de código.
#
# OJO: .yarnrc.yml TIENE que copiarse aquí, antes del install. Si no, la instalación usa los
# ajustes por defecto de Yarn, que son PnP, y crea un .pnp.cjs en vez de node_modules. Luego
# el COPY de abajo trae el .yarnrc.yml (con nodeLinker: node-modules) y el build se encuentra
# sin node_modules y sin estado: «Couldn't find the node_modules state file».
COPY frontend/package.json frontend/yarn.lock frontend/.yarnrc.yml ./
RUN yarn install

COPY frontend/ ./

# El build de producción lee frontend/.env.production (VITE_API_URL=/api). Si ese fichero
# no llegara, src/apiBase.ts ya usa /api por defecto, así que saldría bien igual.
RUN yarn build

# ---------------------------------------------------------------- 2. servir
FROM nginx:1.27-alpine

# La config con el proxy /api hacia el contenedor de la API. Se copia dentro de la imagen
# para que funcione aunque no se monte nada; en el compose se monta encima, así se puede
# retocar sin reconstruir.
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/build /usr/share/nginx/html
RUN chmod -R a+rX /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
