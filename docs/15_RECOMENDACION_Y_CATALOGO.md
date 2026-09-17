# 🎯 RadioNano · Personalización real y crecimiento del catálogo

> Escrito el 2026-08-30 tras auditar **el código y la base de datos reales**. Contiene lo que ya
> existe, lo que parece existir pero está hueco, y la orden de trabajo para completarlo.
>
> Esta es la última pieza grande del proyecto: convertir "un reproductor con mi música" en
> "un reproductor que me conoce".

---

---

# ⚡ CÓMO SE EJECUTA ESTE BLOQUE (leer antes que nada)

## Regla nueva: **no preguntes, decide**

Este documento tiene **todas las decisiones ya tomadas**. No hay nada que consultar. Si aparece una
duda, la respuesta está en §D (Decisiones ya tomadas) o se resuelve con la regla general:
**elige la opción más simple que cumpla el criterio de aceptación, anótala en `PROGRESS.md` y sigue.**

**Una entrega = un bloque entero (C, R, T, U).** No se reporta entre tareas. No se pide confirmación.
Al cerrar el bloque: tabla de tarea → estado → ficheros, y nada más.

## Lo que NO se puede hacer desde el sandbox (comprobado, no supuesto)

Ni el entorno del agente ni el de Claude alcanzan la red de terceros:

```
api.deezer.com        → sin conexión
itunes.apple.com      → sin conexión
youtube.com           → sin conexión
```

**La máquina de David sí llega** (es como el recolector ha bajado 2.268 canciones). Por tanto:

| Tipo de tarea | Quién la ejecuta |
|---|---|
| Escribir código, tests, migraciones, lógica de mixes | **el agente** |
| Cualquier cosa que llame a Deezer/Apple/YouTube o descargue audio | **David**, con un script |

**Consecuencia práctica**: todo lo que necesite red se entrega como **script con `--dry-run` y
`--apply`**, probado con datos falsos (*fixtures*), y David lo ejecuta. **El agente nunca se bloquea
esperando red**: escribe el script, escribe su test con fixtures, y pasa a la tarea siguiente.

---

# §D · Decisiones ya tomadas (no consultar)

| # | Duda | Respuesta |
|---|---|---|
| D1 | ¿Rellenar `artists.genre` desde Deezer? | **Sí**, en un script aparte (`scripts/generos_artistas.py`) que **ejecuta David**. El agente lo escribe y lo prueba con fixtures. |
| D2 | ¿Aplicar ya los 274 cambios seguros de C5? | **Sí.** Se aplican con `--apply`. Los ~116 que se queden en `other` se resuelven después, cuando David haya rellenado los géneros de artista. |
| D3 | ¿Qué pasa si un tema no se puede clasificar? | Se queda en **`other`**. Nunca se inventa un género. |
| D4 | ¿API de Spotify? | **No.** Apple + Deezer + Los 40 + YouTube ya están integrados y no piden credenciales. |
| D5 | ¿Cuántos mixes por usuario? | Los **6** de la tabla de R2. Ni más ni menos. |
| D6 | ¿Cuántas canciones por mix? | 25 los diarios, 30 el de descubrimiento, 50 los tops. |
| D7 | ¿Dónde se guardan los mixes? | Tabla `mixes`, con `kind`, `tracks_json`, `explicacion` y `created_at`. Se sirven de ahí, no se calculan por petición. |
| D8 | ¿Qué hace un mix si el usuario no tiene señales? | La regla de arranque en frío de R4 (popularidad + variedad forzada). Nunca una lista vacía. |
| D9 | ¿Se borran los mixes viejos? | `prune` ya lo hace a los 30 días. No tocar. |
| D10 | ¿Se puede bajar el listón de calidad para llenar el catálogo? | **No.** `quality.revisar()` y el análisis de audio son innegociables. |
| D11 | ¿Techo de disco? | **60 GB** en `E:\Musica`. El recolector se para al llegar. |
| D12 | ¿Cuántas descargas al día? | **150**, repartidas según C1. |

---

# §TOP · Bloque nuevo: Tops y listas que se nutren de fuera

David lo ha pedido explícitamente: que la app tenga **tops** y que se alimente de lo que ya existe en
otras aplicaciones. Todo esto son playlists `type='system'`, regeneradas por el worker.

## TOP1 · Tops que vienen de fuera

| Playlist | Fuente (ya integrada en `radiov/`) | Cadencia |
|---|---|---|
| **Top España** | Apple RSS `es` | 12 h |
| **Top Global** | Apple RSS `us` + `gb` + `mx` combinados y deduplicados | 12 h |
| **Top Latino** | Apple RSS `mx` + `ar` + `co` | 12 h |
| **Los 40 Principales** | `radiov/charts.py::los40_top` | 24 h |
| **Novedades Deezer** | editorial/releases de `radiov/deezer.py` | 24 h |
| **Tendencia en YouTube** | `yt-dlp` sobre la lista de música en tendencia | 24 h |

Cada una: se emparejan los temas con el catálogo (T1, emparejado tolerante) y **lo que no está se
encola en `requests`** para que el recolector lo baje (T2). Así los tops llenan el catálogo solos.

## TOP2 · Tops de la propia casa (los más valiosos)

Estos no dependen de nadie y son los que hacen que la app se sienta *tuya*:

| Playlist | Regla |
|---|---|
| **Lo más escuchado de la casa** | agregado de `plays` de **todos** los usuarios, últimos 30 días |
| **Top {usuario}** | las 50 más escuchadas de cada usuario (su top personal) |
| **Subiendo** | las que más han crecido en reproducciones esta semana respecto a la anterior |
| **Rescatadas** | en el catálogo hace >90 días y nunca reproducidas: el fondo de armario |

## TOP3 · Tops por corte

**Por género** (uno por cada género con más de 30 canciones) y **por década** (60s a 20s), ordenados
por `rank` y con diversidad de artista. Salen gratis de `smart_playlists`.

---


## 1. Diagnóstico: hay andamio, no hay casa

El worker tiene siete tareas y las tablas están creadas. Pero al mirar dentro:

| Tabla | Filas | Qué significa |
|---|---|---|
| `mixes` | **0** | nunca se ha generado un mix |
| `smart_playlists` | **0** | ni una regla |
| `playlists` tipo `system` | **0** | no hay "Trending" ni "Novedades" |
| `playlist_tracks` | **0** | ninguna lista tiene contenido |
| `plays` | **0** | **no hay historial de escucha** |
| `similar` | 49.640 | ✅ esto sí funciona (la radio) |

### 1.1 🔴 `rebuild_mixes` no personaliza nada

```python
ids = [... .order_by(models.Track.rank.desc()).limit(20)]
```

Coge **las 20 más populares** excluyendo lo escuchado en 7 días. **No mira el perfil de gustos.**
Dos usuarios con gustos opuestos reciben la misma lista. Y `personalization.py` —que ya tiene
recencia, señales implícitas, arranque en frío y diversidad MMR— **no se usa aquí**.

### 1.2 🔴 `refresh_trends` no puede encontrar casi nada

```python
t = db.query(models.Track).filter(models.Track.artist == h.get("artist"),
                                  models.Track.title == h.get("title")).first()
```

Igualdad **exacta** de cadenas contra los títulos de Apple. Con acentos, "feat.", mayúsculas y
paréntesis, esto acierta casi nunca. Y cuando no encuentra la canción, **no hace nada**: no la
encola para descargar. Las tendencias no alimentan el catálogo.

### 1.3 🔴 `rebuild_static_lists` crea la regla y se olvida del contenido

Inserta dos filas en `smart_playlists` ("Novedades", "Energy Boost") y **nunca genera sus canciones**.
Son listas vacías con nombre bonito.

### 1.4 🟠 Sin historial no hay personalización posible

`plays = 0`. Hasta que la app se use de verdad, cualquier "para ti" es una lista de populares. Esto
**no es un fallo**, es el arranque en frío — pero hay que diseñarlo para que en ese estado la app
siga siendo buena, y para que mejore visiblemente a medida que se usa.

### 1.5 Estado del catálogo

2.268 canciones · 17,9 GB · **6.075 artistas en la cola** (`artist_pool`) sin explorar. El recolector
tiene combustible de sobra; lo que falta es dirigirlo.

---

## 2. Lo que hay que construir

### BLOQUE R · Mixes de verdad, por usuario y por periodo

**R1 · `rebuild_mixes` usa el perfil de gustos.** Sustituir el `order_by(rank)` por
`personalization.señales()` + `_score()` + `seleccionar_diverso()`, que ya existen y están probados.

**R2 · Varios mixes, no uno.** Cada uno con su cadencia y su criterio:

| `kind` | Nombre visible | Qué contiene | Cadencia |
|---|---|---|---|
| `daily_1/2/3` | Mix diario 1, 2, 3 | tres mixes de ~25 temas, **cada uno anclado a un grupo de géneros distinto** de los que más escucha (así son tres listas que suenan diferente, no tres cortes de la misma) | diaria, 05:00 |
| `discover` | Descubrimiento semanal | 30 temas que **nunca ha escuchado**, afines a su perfil pero de artistas que no están en sus preferidos | lunes 05:00 |
| `on_repeat` | En bucle | lo más escuchado en los últimos 30 días | diaria |
| `time_capsule` | Cápsula del tiempo | sus géneros preferidos, pero filtrado a `era` anterior a 2010 | mensual, día 1 |
| `radar` | Radar de novedades | temas con `release_date` de los últimos 60 días afines al perfil | semanal |

**R3 · Semilla estable por día.** El mix del día **no puede cambiar** cada vez que se recarga la
página. Usar `random.Random(f"{user_id}-{fecha}")` como semilla, y guardar el resultado en `mixes`.

**R4 · Arranque en frío que no dé pena.** Con menos de 10 señales, mezclar popularidad (`rank`) con
**variedad forzada**: máximo 2 por artista, y al menos 4 géneros y 3 eras distintas en la lista. Es
mejor que 20 reguetones de 2024 seguidos.

**R5 · Que se note que aprende.** Añadir `mixes.explicacion` (texto corto): *"porque escuchas mucho
a Estopa"*, *"porque te gustó Rosalía"*. La app lo enseña bajo el título del mix. Es lo que hace que
la personalización se *perciba*, no solo exista.

### BLOQUE T · Tendencias que además alimentan el catálogo

**T1 · Emparejado tolerante.** Normalizar antes de comparar: minúsculas, sin tildes, sin
`(feat. …)`, `[Remaster]`, `- Radio Edit`, signos de puntuación. Comparar por `(artista, título)`
normalizados y, si falla, por similitud (`difflib.SequenceMatcher > 0.87`). Reutilizar lo que ya
hace `radiov` para deduplicar.

**T2 · Lo que no está, se pide.** Si un tema de la lista de éxitos no está en el catálogo, insertarlo
en `requests` (la tabla ya existe) con `source='trending'`. El recolector consume esa cola con
prioridad. **Así las tendencias hacen crecer el catálogo solas.**

**T3 · Más fuentes de tendencias.** Ya hay Apple (por país) y Los 40 en `radiov/charts.py`. Añadir:
- **Deezer** charts y editorial (el cliente ya está en `radiov/deezer.py`).
- **YouTube** música en tendencia, vía `yt-dlp` sobre la lista de tendencias musicales.
- Los 40 por lista (Dance, Urban…), que ya se descarga.

> ⚠️ **Spotify no.** Su API pide credenciales de aplicación y renovarlas, y todo el proyecto se ha
> construido para no depender de ellos. Apple + Deezer + YouTube + Los 40 cubren lo mismo. Si algún
> día se quiere, se añade como una fuente más, no como el eje.

**T4 · Playlists del sistema con contenido real.** `rebuild_static_lists` debe **generar
`playlist_tracks`** ejecutando el JSON de `smart_playlists`. Listas iniciales:
`Trending`, `Novedades`, `Los 2000`, `Fiesta`, `Tranquilo`, `Para el gimnasio`, `En español`,
`Clásicos` — cada una con su regla de género/era/energía/tags.

### BLOQUE C · Poner el recolector a producir

**C1 · Vaciar la cola de artistas.** Hay **6.075 artistas** en `artist_pool` sin explorar. Configurar
el agente para que descargue de forma sostenida (p. ej. 100-200 temas al día) priorizando:
1. la cola de `requests` (lo que piden los usuarios y las tendencias),
2. artistas que el usuario ya escucha y de los que hay pocas canciones,
3. `artist_pool` por popularidad.

**C2 · Equilibrar por décadas.** Hoy el catálogo está muy sesgado a lo reciente (20s: 483 · 90s: 53 ·
80s: 29 · 70s: 15 · 60s: 3). Reservar una cuota —**1 de cada 4 descargas para pre-2000**— o las
secciones "Clásicos" y "Cápsula del tiempo" nacerán vacías.

**C3 · Sin bajar el listón de calidad.** Todo lo nuevo pasa por `quality.revisar()` y por el análisis
(`rms`, `gain_db`, `energy` por percentil). **Enganchar `analisis_audio` al final de cada lote de
descarga**, para que nunca vuelva a acumularse una deuda de 2.000 ficheros sin analizar.

**C4 · Metadatos completos.** Ninguna canción entra al catálogo público sin: `year`, `genre`,
`language`, `bpm`, `energy`, `gain_db`, `duration` y carátula. Si falta algo, `status='incompleta'`
y el revisor la completa antes de publicarla.

**C5 · Arreglar la clasificación de género (T-27).** Sigue pendiente y ahora importa más: si los
mixes se construyen por género, un género mal etiquetado envenena la recomendación. `/tracks?genre=
reggaeton` devuelve Tory Lanez. 144 canciones en `other`. Reclasificar con los géneros de Deezer del
artista + el álbum, no solo con el del tema.

### BLOQUE U · Que se vea en la app

**U1 · `GET /playlists/system`** con portada y descripción.
**U2 · `GET /mixes`** → los mixes del usuario con su `kind`, nombre, portada y `explicacion`.
**U3 · Fila "Hecho para ti"** en la portada, con los mixes; y **"Novedades"** y **"Tendencias"** con
las del sistema.
**U4 · Portadas generadas** para los mixes: mosaico 2×2 con las carátulas de sus cuatro primeras
canciones. Sin esto todas las listas se ven iguales y no apetece entrar.

---

## 3. Pruebas (sin esto no se cierra)

1. **Dos usuarios con gustos opuestos reciben mixes distintos.** Sembrar el usuario A con likes de
   flamenco y el B con likes de reguetón, ejecutar `rebuild_mixes`, y afirmar que **la intersección
   de sus mixes es menor del 30 %**. Es *la* prueba de que la personalización existe.
2. **El mix del día es estable**: ejecutar dos veces el mismo día → mismo resultado.
3. **Diversidad**: ningún mix tiene más de 2 canciones del mismo artista.
4. **Arranque en frío**: un usuario sin señales recibe un mix con ≥4 géneros y ≥3 eras.
5. **Emparejado de tendencias**: `"Rosalía"/"DESPECHÁ"` empareja con `"Rosalia"/"Despecha (feat. X)"`.
6. **Las tendencias piden lo que falta**: un tema ausente aparece en `requests`.
7. **Las listas del sistema tienen canciones**: `playlist_tracks` > 0 para cada una.
8. **La puerta de calidad sigue activa**: nada sin `gain_db` o sin género llega al catálogo público.

---

## 4. Orden sugerido

```
1. C5 · arreglar géneros        ← primero: los mixes se construyen sobre esto
2. R1+R3+R4 · mixes reales, estables y con buen arranque en frío
3. T1+T2 · emparejado tolerante + pedir lo que falta
4. T4 · listas del sistema con contenido
5. R2+R5 · los cinco tipos de mix + la explicación
6. C1+C2+C3+C4 · el recolector produciendo con calidad y equilibrio
7. U1-U4 · enseñarlo en la app
8. Las 8 pruebas
```

**Aviso de disco**: 2.268 temas ocupan 17,9 GB. A 5.000 serán ~40 GB, a 10.000 unos 80. Conviene
decidir el techo antes de soltar al recolector.


---

# §E · Orden de ejecución definitiva y criterios medibles

Cuatro entregas. Dentro de cada una **no se para**.

## ENTREGA 1 · Géneros y mixes reales  (C5 + R1 + R3 + R4)

- C5 · aplicar el backfill de géneros ya escrito (`--apply`) y escribir `scripts/generos_artistas.py`
  (rellena `artists.genre` desde Deezer; **lo ejecuta David**), con test de fixtures.
- R1 · `rebuild_mixes` usa `personalization.señales/_score/seleccionar_diverso`. Fuera el `order_by(rank)`.
- R3 · semilla `random.Random(f"{user_id}-{fecha}")` y resultado guardado en `mixes`.
- R4 · arranque en frío: ≥4 géneros y ≥3 eras, máximo 2 por artista.

**Aceptación** · dos usuarios con gustos opuestos → intersección de mixes **< 30 %** · el mix del día
no cambia al reejecutar · `other` baja de 144 a ≤116 sin inventar géneros.

## ENTREGA 2 · Tendencias y tops  (T1 + T2 + T4 + TOP1 + TOP2 + TOP3)

- T1 · emparejado tolerante (sin tildes, sin `feat.`, `difflib > 0.87`).
- T2 · lo que no está → `requests` con `source='trending'`.
- T4 + TOP · las playlists del sistema **con contenido real** en `playlist_tracks`.

**Aceptación** · `"Rosalia"/"Despecha (feat. X)"` empareja con `"Rosalía"/"DESPECHÁ"` ·
`GET /playlists/system` devuelve **≥12 listas, todas con canciones** · un tema ausente aparece en `requests`.

## ENTREGA 3 · Los seis mixes y el recolector  (R2 + R5 + C1-C4)

- R2 · los 6 tipos · R5 · `mixes.explicacion` ("porque escuchas mucho a Estopa").
- C1-C4 · el recolector consume `requests` primero, cuota de 1 de cada 4 para pre-2000, análisis de
  audio enganchado al final de cada lote, y nada entra sin metadatos completos.

**Aceptación** · cada usuario tiene 6 mixes con explicación · tras un lote de descarga no queda
ninguna canción sin `gain_db` ni sin género.

## ENTREGA 4 · La app  (U1-U4 + las 8 pruebas)

- U1-U4 · `/playlists/system`, `/mixes`, la fila "Hecho para ti" y las portadas en mosaico 2×2.
- Las 8 pruebas de §3 + un e2e nuevo: la portada muestra los mixes y al pulsar uno, suena.

**Aceptación** · `npm run test:todo` y `pytest` en verde, con las 8 pruebas nuevas incluidas.

---

## ✅ Estado de las entregas (2026-08-30)

| Entrega | Estado | Qué falta exactamente |
|---|---|---|
| **1** · Géneros y mixes reales | ✅ **completa** | — (C5 `other`→0; R1+R3+R4 + tests) |
| **2** · Tendencias y tops | ✅ **completa** | — (T1+T2+T4+TOP1/2/3 + tests) |
| **3** · Seis mixes y recolector | 🚧 **parcial** | Faltan **C1** (prioridad `requests`→artistas escuchados→`artist_pool` en el bucle de descarga del recolector) y **C3** (enganchar `analisis_audio` al final de cada lote; hoy lo cubre en parte el mantenimiento del agente). Hechos: R2+R5, config D11/D12/C2/C4, compuerta C4, helper de cuota C2. |
| **4** · La app | 🚧 **parcial** | Faltan **U4** (portadas en mosaico 2×2) y el **e2e** nuevo. Hechos: U1 (`/playlists/system`), U2 (`/mixes`), U3 (fila "Hecho para ti" en la portada), la mayoría de las 8 pruebas. |

**Por qué se aparcan C1 y U4+e2e** (decisión de David, no abandono): solo se pueden verificar de verdad con el recolector corriendo en la máquina de David y con **mixes reales generados**, y ahora mismo `plays = 0` (no hay historial del que aprender). Seguir puliendo la presentación de unos mixes que nadie ha generado es trabajo a ciegas. El sistema de recomendación está construido y probado en vacío; la evaluación real llega cuando David use la app (escuchar, dar me gusta, saltar) una semana, y entonces `/mixes` deje de ser arranque en frío.

**Suite en verde** (verificado por David): 46 e2e + 11 unitarias + 49 backend.

---

## Lo que ejecuta David (scripts que necesitan red o disco)

```powershell
.venv\Scripts\python.exe scripts\reclasificar_generos.py --apply     # C5
.venv\Scripts\python.exe scripts\generos_artistas.py --apply         # rellena artists.genre (Deezer)
.venv\Scripts\python.exe scripts\reclasificar_generos.py --apply     # C5 otra vez, ya con géneros
# y reanudar el recolector con la nueva configuración
```

El agente **escribe y prueba** estos scripts con fixtures; **no espera** a que se ejecuten para
continuar con la tarea siguiente.
