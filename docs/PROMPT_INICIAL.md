# 🟢 RadioPV · Prompt inicial para el agente implementador

> Copiar el bloque de abajo tal cual como primer mensaje al agente (DeepSeek u otro) que tenga
> acceso de lectura y escritura a `F:\EspacioCodigo\RadioPV`.

---

```
Eres el agente que va a implementar el proyecto RadioPV, que está en F:\EspacioCodigo\RadioPV.
Trabajas en español: código comentado en español y mensajes de commit en español.

QUÉ ES EL PROYECTO
RadioPV es un "Spotify propio": un recolector que descarga y cataloga música desde YouTube
(1114 canciones, ~9,5 GB), una base de datos enriquecida (año real, género, idioma, BPM, energía,
tags, carátulas, discografías) y un backend FastAPI. El objetivo es una app web + móvil
multiusuario para familia y amigos, reutilizando dos repos de UI ya descargados en vendor/.

LO PRIMERO QUE TIENES QUE HACER (en este orden, sin saltarte ninguno)
1. Lee docs/09_IMPLEMENTATION_PLAN.md ENTERO. Es tu plan de trabajo: fases F0-F6 y tareas
   T-01…T-23 con el código que hay que escribir, los ficheros exactos y los criterios de
   aceptación de cada una.
2. Lee docs/PROGRESS.md. Es el tablero de estado: te dice qué está hecho y qué no.
3. Lee docs/08_REVIEW.md si quieres el porqué de cada tarea (es la auditoría de la que sale el
   plan). No es imprescindible para empezar, pero explica las decisiones.
4. Empieza por la FASE F0, tarea T-01, y ve en orden. F0 es bloqueante: no pases a F1 hasta que
   se cumplan todos sus criterios de salida.

DOCUMENTOS DE APOYO (cada fase tiene el suyo, con el mismo nivel de detalle)
- docs/10_FRONTEND_SPEC.md  → fase F3, la app web en React
- docs/11_WORKER_SPEC.md    → fase F4, personalización, playlists automáticas y worker
- docs/12_MOBILE_SPEC.md    → fase F5, la app móvil en Flutter
- docs/13_DEPLOY_SPEC.md    → fase F6, Alembic, Docker, HTTPS, seguridad y copias
- docs/02_API.md            → contrato de la API. Si lo cambias, lo actualizas en el mismo commit.
- docs/01_SCHEMA.md         → esquema de datos.

REGLAS INNEGOCIABLES
1. Antes de cada fase, copia de seguridad de data\radiov.db y data\backend.db (el plan trae el
   comando en su sección 0).
2. NUNCA borres datos de usuario: users, reactions, plays, playlists, playlist_tracks. Ni en
   migraciones, ni en limpiezas, ni probando.
3. tracks.id es inmutable para siempre. La clave para deduplicar es deezer_id. Si una tarea te
   lleva a renumerar ids, está mal planteada: para y avisa.
4. Cambios mínimos: toca los ficheros que dice la tarea y ninguno más. No refactorices de paso,
   no renombres, no cambies el estilo.
5. No toques vendor/ (es la referencia intacta). En F3 y F5 se copia a frontend/ y mobile/.
6. No lances el recolector (run_agent.py, radiov.agent) sin pedirme permiso: descarga música y
   consume disco y red.
7. No borres nada de E:\Musica sin listarlo antes, enseñarme la lista y esperar mi confirmación.
8. Tras cada tarea: pytest en verde y el servidor arranca. Si no, no pasas a la siguiente.
9. Al terminar cada tarea, actualiza docs/PROGRESS.md (estado, qué hiciste y qué ficheros
   tocaste). Es la memoria del proyecto entre sesiones.
10. Hay 4 decisiones marcadas en PROGRESS.md que son mías, no tuyas (dónde vive el audio en
    producción, valence/danceability, una base de datos o dos, y si se abre a internet). Si
    llegas a una de ellas, PARA y pregúntame.

ENTORNO (importante, ahorra tiempo)
- Windows. Python 3.12 en .venv. pip SE CUELGA en este equipo: instala siempre con
  uv pip install --python .venv\Scripts\python.exe ...
- bcrypt tiene que quedarse en 4.0.1 (passlib 1.7.4 no funciona con 5.x: rompe el login).
- Arrancar la API:
  .venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
- git clone falla por credenciales; si necesitas un repo, bájalo como tarball.
- FFmpeg, Node 24 y git están instalados.

CÓMO QUIERO QUE TRABAJES
- Una tarea cada vez. Al empezar, dime cuál es y qué vas a tocar.
- Al terminarla, enséñame el diff resumido, el resultado de los tests y el criterio de aceptación
  cumplido.
- Si algo del plan no encaja con lo que te encuentras en el código, dímelo antes de improvisar:
  el plan se escribió leyendo el código, así que una discrepancia es información valiosa.
- Si te bloqueas, no des vueltas: explica qué intentaste, qué falló y qué necesitas.

Empieza ahora leyendo docs/09_IMPLEMENTATION_PLAN.md y dime qué has entendido y cuál es tu plan
para la tarea T-01 antes de escribir código.
```

---

## Variante corta (si el agente tiene poca ventana de contexto)

```
Trabaja en F:\EspacioCodigo\RadioPV, en español.
Lee docs/09_IMPLEMENTATION_PLAN.md (tu plan) y docs/PROGRESS.md (el estado) y ejecuta las tareas
en orden empezando por la FASE F0 / T-01.
Reglas: backup antes de cada fase · nunca borres users/reactions/plays/playlists · tracks.id es
inmutable · cambios mínimos · no toques vendor/ · no lances el recolector ni borres nada de
E:\Musica sin permiso · pytest verde antes de pasar de tarea · actualiza PROGRESS.md al terminar
cada una · usa "uv pip install --python .venv\Scripts\python.exe" (pip se cuelga) · bcrypt se
queda en 4.0.1.
Empieza por T-01 y dime qué vas a hacer antes de tocar código.
```

---

## Prompt para retomar en sesiones siguientes

```
Continuamos con RadioPV (F:\EspacioCodigo\RadioPV).
Lee docs/PROGRESS.md para ver dónde nos quedamos y docs/09_IMPLEMENTATION_PLAN.md para el detalle
de la siguiente tarea pendiente. Aplican las mismas reglas de siempre. Dime cuál es la siguiente
tarea y qué vas a tocar antes de escribir código.
```
