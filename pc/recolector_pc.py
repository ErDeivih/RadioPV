"""Recolector que corre en el PC de casa y manda la música al servidor.

POR QUÉ ESTO Y NO EL SERVIDOR
-----------------------------
El servidor es un portátil de 4 GB sin swap. Descargar música es lo que más le pesa: yt-dlp
(también es Python), ffmpeg para el análisis, y el disco escribiendo cientos de megas. Y el PC de
casa está encendido igualmente, con muchísima más máquina y un disco grande.

Así que el trabajo se reparte:

    PC  · buscar, descargar, etiquetar y analizar   → es lo pesado
    PC  · mandar los ficheros y las fichas al servidor
    SERVIDOR · lo que sólo él puede hacer: servir la aplicación, generar listas y mixes,
               guardar la biblioteca y hacer de archivo

El PC usa **el mismo código** que usaba el servidor (`radiov`), no una copia: así las reglas de
calidad, las semillas y el etiquetado son los mismos en las dos máquinas.

CÓMO SE USA
-----------
    1) Copia `pc/config.ejemplo.json` a `pc/config.json` y rellena el token.
    2) (.venv) python pc/recolector_pc.py --una-vuelta      # una pasada y sale
       (.venv) python pc/recolector_pc.py                   # en bucle, para dejar encendido
       (.venv) python pc/recolector_pc.py --solo-sembrar    # sólo sincroniza lo que ya hay

El token se pide en el servidor una vez y se guarda en `pc/config.json` (que NO va a git).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# El paquete `radiov` vive en la raíz del repositorio y este guion está en `pc/`: sin esto, el
# intérprete busca `radiov` sólo en `pc/` y falla con «No module named 'radiov'».
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

CONFIG_PATH = RAIZ / "pc" / "config.json"
CONFIG_EJEMPLO = RAIZ / "pc" / "config.ejemplo.json"


# --------------------------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------------------------
class _Duplicador:
    """Escribe a la vez en la consola y en el fichero de registro.

    Hace falta porque esto corre como **tarea programada de Windows**, que no guarda la salida en
    ninguna parte: sin registro, un fallo del recolector del PC es invisible (nadie ve el error, y
    lo único que se nota es que la música deja de llegar). Es el mismo tipo de fallo silencioso que
    ya apareció con el recolector del servidor.
    """

    def __init__(self, original, fichero):
        self.original = original
        self.fichero = fichero

    def write(self, texto):
        self.original.write(texto)
        try:
            self.fichero.write(texto)
            self.fichero.flush()
        except Exception:  # noqa: BLE001
            pass

    def flush(self):
        self.original.flush()
        try:
            self.fichero.flush()
        except Exception:  # noqa: BLE001
            pass

    def reconfigure(self, **kw):
        """La consola admite `reconfigure`; el fichero no, así que se ignora."""
        if hasattr(self.original, "reconfigure"):
            self.original.reconfigure(**kw)


def preparar_salida(fichero_log: Path | None = None) -> None:
    """La consola de Windows usa cp1252 por defecto y **revienta** al imprimir ciertos caracteres.

    Pasó de verdad: el guion terminaba la vuelta entera y luego moría con
    «'charmap' codec can't encode character '\\u2192'» al escribir una flecha en un mensaje. La
    recolección había ido bien, pero el script salía con error y no se enviaba nada.
    """
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass

    if fichero_log is not None:
        try:
            fichero_log.parent.mkdir(parents=True, exist_ok=True)
            manejador = open(fichero_log, "a", encoding="utf-8")
            sys.stdout = _Duplicador(sys.stdout, manejador)         # type: ignore[assignment]
            sys.stderr = _Duplicador(sys.stderr, manejador)         # type: ignore[assignment]
            print(f"\n===== vuelta {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
        except Exception:  # noqa: BLE001
            pass


def cargar_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"Falta {CONFIG_PATH}. Copia {CONFIG_EJEMPLO.name} a config.json y rellénalo.")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    faltan = [k for k in ("api", "token", "servidor", "musica_local", "datos_locales") if not cfg.get(k)]
    if faltan:
        sys.exit(f"En {CONFIG_PATH} faltan: {', '.join(faltan)}")
    return cfg


def preparar_entorno(cfg: dict) -> None:
    """El entorno tiene que estar puesto ANTES de importar `radiov`: `config.py` lee las rutas al
    cargarse, así que si se cambian después no sirven de nada."""
    os.environ["RADIOPV_DATA_DIR"] = cfg["datos_locales"]
    os.environ["RADIOPV_BASE_MUSIC"] = cfg["musica_local"]
    os.environ.setdefault("RADIOPV_ENV", "prod")
    Path(cfg["datos_locales"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["musica_local"]).mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------------------------
# Hablar con el servidor
# --------------------------------------------------------------------------------------------
def pedir(cfg: dict, ruta: str, *, datos: dict | None = None) -> dict:
    import requests

    url = f"{cfg['api'].rstrip('/')}/{ruta.lstrip('/')}"
    cab = {"X-Ingest-Token": cfg["token"], "Content-Type": "application/json"}
    if datos is None:
        r = requests.get(url, headers=cab, timeout=120)
    else:
        r = requests.post(url, headers=cab, json=datos, timeout=300)
    if r.status_code == 401:
        sys.exit("El servidor rechaza el token (revisa `token` en pc/config.json).")
    if r.status_code == 503:
        sys.exit("El servidor tiene apagada la ingesta desde otro equipo "
                 "(falta RADIOPV_INGEST_TOKEN en su .env).")
    r.raise_for_status()
    return r.json()


def estado_servidor(cfg: dict) -> dict:
    import requests
    r = requests.get(f"{cfg['api'].rstrip('/')}/collector/estado", timeout=30)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------------------------
# Hasta dónde hemos visto: para pedir al servidor SÓLO lo nuevo
# --------------------------------------------------------------------------------------------
def _ruta_estado_indice(cfg: dict) -> Path:
    return Path(cfg["datos_locales"]) / "indice_estado.json"


def _leer_estado_indice(cfg: dict) -> dict:
    """Recuerda el último id del catálogo del servidor que ya nos trajimos.

    Con eso, cada vuelta pregunta «¿qué has añadido desde entonces?» en vez de traerse las 6.000
    canciones enteras. El servidor lo agradece (es un portátil de 4 GB) y el PC también.
    """
    try:
        return json.loads(_ruta_estado_indice(cfg).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _guardar_estado_indice(cfg: dict, max_id: int) -> None:
    try:
        ruta = _ruta_estado_indice(cfg)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"max_id": int(max_id), "cuando": time.time()}),
                        encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  AVISO: no se pudo guardar hasta dónde se leyó el índice: {e}")


# --------------------------------------------------------------------------------------------
# Sembrar: que el PC sepa lo que YA hay, para no volver a bajarlo
# --------------------------------------------------------------------------------------------
def sembrar(cfg: dict) -> int:
    """Trae la lista de lo que ya está y la mete como fichas vacías en la base local.

    Sin esto el PC volvería a descargar lo que el servidor ya tiene: la comprobación de duplicados
    del recolector (`get_track_id_by_artist_title`) mira SU base, y la del PC empieza vacía.
    Las fichas van sin `file_path` a propósito: son un «esto ya lo tenemos», no una canción.
    """
    from radiov import db as rdb
    from radiov.config import CATALOG_DIR, PLAYLIST_DIR, RAW_DIR, SETTINGS_PATH, save_settings

    ajustes = pedir(cfg, "collector/ajustes")

    # Las rutas se reescriben aquí, a las de ESTA máquina. Aunque el servidor ya no las manda, se
    # deja puesto: un `settings.json` viejo (de antes de este arreglo) traía las del servidor y el
    # PC acababa guardando la música en `F:\music\…` en vez de en su carpeta.
    ajustes["base_music_dir"] = cfg["musica_local"]
    ajustes["download_dir"] = str(RAW_DIR)
    ajustes["catalog_dir"] = str(CATALOG_DIR)
    ajustes["playlist_dir"] = str(PLAYLIST_DIR)
    save_settings(ajustes)

    print(f"  ajustes del servidor guardados en {SETTINGS_PATH}")
    print(f"  rutas locales: catalogada={CATALOG_DIR} · descargas={RAW_DIR}")

    # SÓLO LO NUEVO. El servidor devuelve las canciones con id mayor que el último que vimos, así que
    # en una vuelta normal son unas pocas filas en vez de 6.000: esto se pide cada 15 minutos y no
    # tiene sentido traerse el catálogo entero para descubrir que no ha cambiado nada. Cada 24 h (o si
    # el fichero de estado no está) se pide entero, para corregir cualquier desajuste.
    estado = _leer_estado_indice(cfg)
    desde = estado.get("max_id", 0)
    if time.time() - float(estado.get("cuando", 0)) > 24 * 3600:
        desde = 0
    indice = pedir(cfg, f"collector/indice?desde_id={int(desde)}")
    con = rdb.get_conn()
    # Las claves de la biblioteca local, de UNA vez: comprobar cada canción del índice contra la base
    # una por una serían miles de consultas por vuelta.
    claves = rdb.indice_de_claves()
    nuevas = 0
    con_ids = 0
    conflictos = 0
    repetidas = 0
    try:
        # Las fichas sembradas llevan TAMBIÉN los identificadores (id de YouTube y de Deezer).
        # Al principio sólo se guardaban artista y título, y el PC volvía a descargar canciones que
        # ya tenía: el recolector mira el id de YouTube antes de bajar nada, y sin ese dato no podía
        # saberlo (o el mismo vídeo aparecía con otro nombre de artista). Se vio comparando los
        # ficheros de las dos máquinas: los del servidor eran más antiguos que los del PC, o sea la
        # misma canción bajada y enviada dos veces.
        for pista in indice["pistas"]:
            # El servidor manda `[id, título, artista, id_youtube, id_deezer]`, pero se aceptan
            # también cuatro campos (sin el id) porque las dos máquinas se actualizan por su cuenta:
            # el PC lee el código del repositorio en el sitio y el servidor se actualiza solo cada
            # 5 minutos, así que hay ratos en los que uno va por delante del otro. Reventar por eso
            # sería dejar de descargar por un detalle de formato.
            if len(pista) >= 5:
                _id_servidor, titulo, artista, yt, dz = pista[0], pista[1], pista[2], pista[3], pista[4]
            elif len(pista) == 4:
                titulo, artista, yt, dz = pista
            else:
                continue
            if not titulo or not artista:
                continue
            yt = yt or None
            dz = dz or None
            # Cada ficha va en su propio try: la tabla tiene un índice único por `youtube_id` y en
            # el catálogo hay canciones distintas que apuntan al MISMO vídeo, así que completar el
            # id de la segunda chocaba con la primera y el error subía hasta arriba. Con eso, la
            # siembra entera se caía, y como la siembra va ANTES de recolectar, el PC se quedaba
            # sin descargar NADA: el recolector llevaba desde las 13:00 muriendo en cada vuelta con
            # «UNIQUE constraint failed: tracks.youtube_id».
            try:
                ya = con.execute("SELECT id, youtube_id FROM tracks WHERE (artist=? AND title=?)"
                                 " OR (youtube_id IS NOT NULL AND youtube_id=?)",
                                 (artista, titulo, yt)).fetchone()
                if ya:
                    # Se completa el id si la ficha estaba sembrada sin él... y sólo si ese vídeo no
                    # lo tiene ya otra ficha (si no, «UNIQUE constraint failed»).
                    if yt and not ya["youtube_id"]:
                        otro = con.execute("SELECT id FROM tracks WHERE youtube_id=? AND id<>?",
                                           (yt, ya["id"])).fetchone()
                        if otro:
                            conflictos += 1
                            continue
                        con.execute("UPDATE tracks SET youtube_id=?, deezer_id=COALESCE(deezer_id, ?) "
                                    "WHERE id=?", (yt, dz, ya["id"]))
                        con_ids += 1
                    continue
                # Antes de sembrar se comprueba con la MISMA norma que usa todo lo demás (vídeo →
                # Deezer → clave normalizada de artista y título): la biblioteca del PC no puede
                # quedarse con dos fichas de la misma canción porque el nombre venga con
                # «(Official Video)» o porque sea otro vídeo del mismo tema.
                if rdb.pista_existente(youtube_id=yt, deezer_id=dz, artist=artista, title=titulo,
                                       claves=claves):
                    repetidas += 1
                    continue
                cur = con.execute(
                    "INSERT OR IGNORE INTO tracks(title, artist, youtube_id, deezer_id, status, source,"
                    " file_path, is_remix) VALUES(?,?,?,?,'descargada','sembrado','',0)",
                    (titulo, artista, yt, dz))
                if cur.rowcount:
                    nuevo_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
                    claves[rdb.clave_cancion(artista, titulo)] = nuevo_id
                nuevas += 1
            except sqlite3.IntegrityError:
                conflictos += 1
            except sqlite3.OperationalError as e:
                # «database is locked» y similares: no se pierde la vuelta entera por una ficha.
                print(f"  AVISO: no se pudo sembrar «{artista} - {titulo}»: {e}")
        con.commit()
    finally:
        con.close()
    _guardar_estado_indice(cfg, indice.get("max_id", desde))
    print(f"  índice del servidor: {indice['total']} canciones en total · {indice.get('nuevas', '?')} "
          f"nuevas desde la última vez · {nuevas} fichas sembradas · {con_ids} identificadores completados"
          + (f" · {repetidas} ya estaban" if repetidas else "")
          + (f" · {conflictos} sin poder completar (el vídeo ya es de otra ficha)" if conflictos else ""))
    return nuevas


# --------------------------------------------------------------------------------------------
# Recolectar
# --------------------------------------------------------------------------------------------
def recolectar(cfg: dict, minutos: float, maximo: int) -> int:
    """Enciende el agente del recolector un rato y devuelve cuántas canciones nuevas entraron."""
    from radiov import db as rdb
    from radiov.agent import get_manager

    con = rdb.get_conn()
    try:
        antes = con.execute("SELECT COUNT(*) FROM tracks WHERE source!='sembrado'").fetchone()[0]
    finally:
        con.close()

    manager = get_manager()
    manager.set_agent(True)
    print(f"  recolectando hasta {minutos:.0f} min o {maximo} canciones nuevas…")

    t0 = time.time()
    while True:
        time.sleep(10)
        con = rdb.get_conn()
        try:
            ahora = con.execute("SELECT COUNT(*) FROM tracks WHERE source!='sembrado'").fetchone()[0]
        finally:
            con.close()
        hechas = ahora - antes
        minutos_pasados = (time.time() - t0) / 60
        if hechas >= maximo or minutos_pasados >= minutos:
            print(f"  paro: {hechas} canciones en {minutos_pasados:.1f} min")
            break

    manager.set_agent(False)
    return max(0, hechas)


def atender_peticiones(cfg: dict, maximo: int = 5) -> int:
    """Descarga las canciones que se han pedido desde la app y contesta qué ha pasado.

    Antes estas peticiones se quedaban en `pendiente` **para siempre**: la app las creaba y nadie
    las recogía (había 21 esperando). Ahora las atiende el recolector del PC.

    Se intenta primero el camino normal (artista y título, con la ficha de Deezer) y, si no sale,
    una **búsqueda directa en YouTube**: es lo que hace falta para lo que se pide muchas veces
    —mashups, remixes, sesiones de DJ—, donde no hay «artista - título» que valga sino un vídeo
    concreto.
    """
    from radiov import db as rdb
    from radiov import pipeline

    try:
        respuesta = pedir(cfg, f"collector/peticiones?limite={maximo}")
    except Exception as e:  # noqa: BLE001
        print(f"  aviso: no se pudieron leer las peticiones: {e}")
        return 0

    peticiones = respuesta.get("peticiones") or []
    if not peticiones:
        return 0

    print(f"  canciones pedidas desde la app: {len(peticiones)}")
    resueltas = 0
    for pet in peticiones:
        texto = (pet.get("text") or "").strip()
        video = (pet.get("youtube_id") or "").strip()
        if not texto and not video:
            continue
        print(f"    piden: «{texto}»" + (f" (vídeo {video} elegido a mano)" if video else ""))
        tid = None
        # ¿Ya está ese vídeo en la biblioteca? Entonces no hay nada que bajar. Pasa más de lo que
        # parece: dos personas piden la misma canción, o alguien la pide después de que el buscador
        # la traiga por semillas. Se vio en el registro: el mismo vídeo bajado dos veces seguidas
        # («piden: «Los Huesos» (vídeo …)» dos veces). Se descarga una vez y se contesta que sí a las
        # dos peticiones.
        if video:
            try:
                from radiov import db as _rdb
                if _rdb.track_exists(video):
                    print("      ya estaba en la biblioteca: no se vuelve a bajar")
                    tid = "ya-estaba"
            except Exception:  # noqa: BLE001
                pass
        # Si el usuario eligió un vídeo CONCRETO en la lista de resultados de la página de pedir
        # canciones, se baja ESE y no se busca por texto: de un mismo tema hay el original, el
        # remix, el directo y veinte subidas, y bajar «la que parezca» es bajar otra cosa.
        if video and tid is None:
            try:
                from radiov import youtube as Y
                from radiov import pipeline as P
                bajado = Y.download_video(video, artist="", title=texto or video)
                if bajado:
                    artista, titulo = P._partir_titulo({"title": texto or bajado.get("title") or ""})
                    bajado["title"] = titulo or bajado.get("title") or texto
                    bajado["artist"] = artista or bajado.get("artist") or ""
                    bajado["duration"] = bajado.get("youtube_duration") or pet.get("duration")
                    genero, idioma = P._resolve_genre_lang(bajado["artist"], bajado["title"], None, None)
                    tid = P._persist_yt(bajado, genre=genero, language=idioma, source="peticion")
            except Exception as e:  # noqa: BLE001
                print(f"      no se pudo bajar el vídeo elegido: {str(e)[:80]}")
        if tid is None and texto:
            try:
                tid = pipeline.process_text(texto, source="peticion")
            except Exception as e:  # noqa: BLE001
                print(f"      el camino normal falló: {str(e)[:80]}")
        if tid is None and texto:
            # Último intento: buscar el texto tal cual en YouTube (mashups, sesiones, cruces).
            try:
                nuevos = pipeline.process_youtube_seed(
                    {"mode": "youtube", "query": texto}, max_downloads=1)
                if nuevos:
                    tid = "buscado-en-youtube"
            except Exception as e:  # noqa: BLE001
                print(f"      la búsqueda en YouTube falló: {str(e)[:80]}")

        estado = "descargada" if tid else "fallida"
        detalle = None if tid else "No se encontró ni en las tiendas de música ni en YouTube"
        try:
            pedir(cfg, f"collector/peticiones/{pet['id']}",
                  datos={"estado": estado, "detalle": detalle})
            resueltas += 1
            print(f"      → {estado}")
        except Exception as e:  # noqa: BLE001
            print(f"      no se pudo contestar la petición: {str(e)[:80]}")

    if resueltas:
        print(f"  peticiones contestadas: {resueltas}")
    return resueltas


# --------------------------------------------------------------------------------------------
# Publicar: mandar los ficheros y las fichas
# --------------------------------------------------------------------------------------------
def _crear_tabla_envios(cfg: dict) -> None:
    from radiov import db as rdb
    con = rdb.get_conn()
    try:
        # Tabla propia del PC: marca lo que ya se mandó, para no repetirlo en cada vuelta.
        con.execute("CREATE TABLE IF NOT EXISTS pc_enviadas (track_id INTEGER PRIMARY KEY, "
                    "enviada_en TEXT)")
        con.commit()
    finally:
        con.close()


def _pendientes(cfg: dict) -> list[dict]:
    """Lo descargado aquí que aún no se ha mandado y YA está completo.

    Sólo se manda lo que está en `descargada` (o sea, con todos sus datos: carátula, BPM y
    ganancia). Las `incompleta` se quedan aquí hasta que el mantenimiento del propio PC las
    termina; así el servidor nunca recibe una canción a medias que no podría publicar.
    El mantenimiento del recolector (`_maybe_maintenance`) es el que las completa, y corre en la
    primera vuelta del agente.
    """
    from radiov import db as rdb
    import sqlite3

    con = rdb.get_conn()
    try:
        con.row_factory = sqlite3.Row
        filas = con.execute(
            """SELECT t.* FROM tracks t
               LEFT JOIN pc_enviadas e ON e.track_id = t.id
               WHERE e.track_id IS NULL AND t.source != 'sembrado'
                 AND t.status = 'descargada'
                 AND t.file_path IS NOT NULL AND t.file_path != ''
               ORDER BY t.id""").fetchall()
        pendientes = [dict(f) for f in filas]

        # Se informa de las que están a medias: si esto crece y no baja, el mantenimiento del PC
        # no está terminando su trabajo y hay que mirarlo (no se pierden, pero no se publican).
        a_medias = con.execute(
            """SELECT COUNT(*) FROM tracks t LEFT JOIN pc_enviadas e ON e.track_id = t.id
               WHERE e.track_id IS NULL AND t.source != 'sembrado' AND t.status != 'descargada'
                 AND t.file_path IS NOT NULL AND t.file_path != ''""").fetchone()[0]
        if a_medias:
            print(f"  (aviso: {a_medias} descargadas aún sin completar; se mandarán cuando lo estén)")
        return pendientes
    finally:
        con.close()


def _enviar_ficheros(cfg: dict, ficheros: list[tuple[Path, str]], destino: str, etiqueta: str) -> int:
    """Manda ficheros al servidor con tar por ssh (un solo viaje, no uno por fichero).

    Se escribe a través de un contenedor porque el directorio del servidor es de root: el usuario
    `david` puede usar docker, y así no hace falta ningún permiso especial ni montar Samba.
    """
    existentes = [(p, n) for p, n in ficheros if p and p.exists()]
    if not existentes:
        return 0

    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tar_path = Path(tmp.name)
    try:
        # El tar se crea con el nombre relativo de dentro (catalogada/…, covers/…), para que al
        # descomprimir en el servidor cada cosa caiga en su sitio.
        with tarfile.open(tar_path, "w") as tar:
            for ruta, nombre in existentes:
                tar.add(str(ruta), arcname=nombre)
        tam_mb = tar_path.stat().st_size / 1024 / 1024
        print(f"  {etiqueta}: {len(existentes)} ficheros ({tam_mb:.1f} MB) hacia {destino}")

        cmd = (f'docker run --rm -i -v "{destino}:/destino" alpine '
               f'tar -xf - -C /destino')
        with open(tar_path, "rb") as f:
            r = subprocess.run(["ssh", cfg["servidor"], cmd], stdin=f,
                               capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            print(f"  AVISO: el envío de {etiqueta} falló: {(r.stderr or '')[:200]}")
            return 0
        return len(existentes)
    finally:
        tar_path.unlink(missing_ok=True)


def revisar_extremos(cfg: dict, maximo: int = 12, buscar_otra: int = 2) -> int:
    """Mira si las canciones bajadas de YouTube traen intro, diálogo o cola que no es la canción.

    POR QUÉ AQUÍ Y NO EN EL SERVIDOR
    --------------------------------
    El audio está en el PC y analizarlo (librosa) come CPU: el servidor es un portátil de 4 GB que
    además sirve la aplicación. Así que lo que se baja aquí se mide aquí, y el resultado viaja con la
    ficha (el servidor repasa en lotes pequeños lo que ya tenía, desde su worker).

    El trabajo de verdad está en `radiov.catalog.revisar_extremos_lote`, que es el mismo que usa el
    servidor: así el PC y el servidor no pueden medir cosas distintas.
    """
    from radiov import catalog as C

    print("  mirando intros y colas de lo bajado…")
    revisadas, con_algo, cambiadas = C.revisar_extremos_lote(
        limit=maximo, buscar_otra=buscar_otra, log=lambda m: print(m))
    if revisadas or con_algo:
        print(f"  revisadas {revisadas} · con algo en los extremos {con_algo} · "
              f"cambiadas por otra versión {cambiadas}")
    return cambiadas


def completar(cfg: dict, maximo: int = 40) -> int:
    """Termina de analizar lo descargado ANTES de mandarlo.

    Una canción recién bajada nace `incompleta`: le faltan la ganancia (`gain_db`, que sale de
    medir el audio con ffmpeg), la energía (percentil del RMS), la carátula y a veces el año. La
    aplicación sólo publica las `descargada`, así que si se mandaran tal cual llegarían para no
    verse: aparecerían en la base del servidor y no en la aplicación, que es la peor forma de
    fallar (todo parece correcto y no se escucha nada).

    Es el mismo mantenimiento que hace el agente, pero aquí explícito y con tope: así el envío no
    depende de que al agente le haya dado tiempo a llegar.
    """
    from radiov import catalog as C

    print("  completando lo descargado (ganancia, energía, carátulas)…")
    e = C.analyze_energy_missing(limit=maximo)
    g = C.analizar_gain_missing(limit=maximo)
    med = C.enrich_media(limit=maximo)
    img = C.fetch_media(limit=maximo)
    rep = C.republicar_completas(limit=600)
    print(f"  energías={e} · ganancias={g} · fichas={med} · imágenes={img} · publicadas={rep}")
    return rep


def publicar(cfg: dict) -> int:
    """Manda lo nuevo al servidor: primero la ficha, y sólo después el audio.

    EL ORDEN ES LO QUE AHORRA TRABAJO
    ---------------------------------
    Antes se subía el audio y luego se pedía permiso: si la canción ya estaba en el servidor (mismo
    tema con otro nombre, otra subida…), se habían subido 5-10 MB para nada y el fichero se quedaba
    en `/music` sin ficha que lo apuntara — disco ocupado y sin rastro. Ahora la ficha va primero
    (pesa unos cientos de bytes), el servidor contesta cuáles ya tenía, y de ésas no se sube nada.
    """
    from radiov import db as rdb

    _crear_tabla_envios(cfg)
    pendientes = _pendientes(cfg)
    if not pendientes:
        print("  nada nuevo que enviar")
        return 0

    musica_local = Path(cfg["musica_local"])
    datos_locales = Path(cfg["datos_locales"])

    # ORDEN IMPORTANTE: PRIMERO LAS FICHAS, DESPUÉS LOS FICHEROS.
    #
    # Antes era al revés (el audio se subía antes de preguntar) y tenía un coste tonto: si una
    # canción ya estaba en el servidor, se subían igualmente sus 5-10 MB de audio… y el servidor
    # rechazaba la ficha, así que ese fichero se quedaba en `/music` **sin ninguna ficha que lo
    # apuntara**: ocupaba disco para siempre y no había forma de saber que estaba ahí.
    #
    # Ahora se manda primero la ficha (son unos cientos de bytes) y el servidor contesta cuáles ya
    # tenía. El audio se sube sólo de las nuevas.
    CAMPOS = ("title", "artist", "album", "year", "genre", "language", "bpm", "energy", "gain_db",
              "valence", "tags", "era", "feat", "duration", "file_path", "file_size", "status",
              "source", "youtube_id", "deezer_id", "cover_url", "cover_path", "artist_id",
              "artist_image_url", "artist_image_path", "is_remix", "analyzed_at", "added_at",
              "match_score", "rms", "rank", "explicit",
              # Lo medido en los extremos (intro/cola): viaja para poder revisarlo en el panel.
              "intro_seg", "cola_seg", "extremos_json", "extremos_revisado", "version_limpia")
    RUTAS = ("file_path", "cover_path", "artist_image_path")
    pistas = []
    for t in pendientes:
        rec = {k: t.get(k) for k in CAMPOS if t.get(k) is not None}
        for k in RUTAS:
            if rec.get(k):
                rec[k] = str(rec[k]).replace("\\", "/")
        pistas.append(rec)

    respuesta = pedir(cfg, "collector/importar", datos={"pistas": pistas, "origen": cfg.get("nombre_pc", "pc")})
    repetidas = int(respuesta.get("repetidas") or 0)
    print(f"  fichas enviadas: {respuesta['total']} · nuevas en el servidor: {respuesta['nuevas']}"
          + (f" · ya estaban allí: {repetidas}" if repetidas else ""))

    # Las que el servidor ya tenía: ni se sube su audio ni sus carátulas (ya están allí).
    ya_en_servidor = {
        (d.get("youtube_id") or "", (d.get("artist") or "").lower(), (d.get("title") or "").lower())
        for d in (respuesta.get("repetidas_detalle") or [])
    }

    def es_nueva(t: dict) -> bool:
        clave = (t.get("youtube_id") or "", (t.get("artist") or "").lower(),
                 (t.get("title") or "").lower())
        return clave not in ya_en_servidor

    a_enviar = [t for t in pendientes if es_nueva(t)]
    if len(a_enviar) != len(pendientes):
        print(f"  ficheros que NO se reenvían (la canción ya estaba): "
              f"{len(pendientes) - len(a_enviar)}")

    audio: list[tuple[Path, str]] = []
    covers: list[tuple[Path, str]] = []
    artistas: list[tuple[Path, str]] = []
    for t in a_enviar:
        fp = (t.get("file_path") or "").replace("\\", "/").strip("/")
        if fp:
            # En el servidor la música vive en la raíz montada: `catalogada/…` tal cual.
            audio.append((musica_local / fp, fp))
        for columna, lista in (("cover_path", covers), ("artist_image_path", artistas)):
            guardado = (t.get(columna) or "").replace("\\", "/")
            if guardado:
                nombre = guardado.split("/")[-1]      # en el servidor sólo se usa el nombre
                sub = "covers" if columna == "cover_path" else "artists"
                lista.append((datos_locales / sub / nombre, nombre))

    _enviar_ficheros(cfg, audio, cfg["musica_servidor"], "música")
    if covers:
        _enviar_ficheros(cfg, covers, cfg["covers_servidor"], "carátulas")
    if artistas:
        _enviar_ficheros(cfg, artistas, cfg["artists_servidor"], "fotos de artistas")

    # Cuando el servidor dice que una canción «ya estaba», es que la teníamos las dos máquinas: en el
    # PC por haberse bajado de nuevo y en el servidor desde antes (mismo vídeo con otro nombre, u otro
    # vídeo del mismo tema). Se apunta en el registro del recolector para poder ver cuántas se repiten
    # y de dónde salen, en vez de que ocurra en silencio.
    if repetidas:
        for detalle in respuesta.get("repetidas_detalle") or []:
            print(f"      ya estaba: {detalle.get('artist')} - {detalle.get('title')}"
                  + (f" (rellenado: {', '.join(detalle['rellenos'])})" if detalle.get("rellenos") else ""))
        try:
            from radiov import db as _rdb

            ejemplos = ", ".join(f"{d.get('artist')} - {d.get('title')}"
                                 for d in (respuesta.get("repetidas_detalle") or [])[:5])
            _rdb.log_event(f"🔁 {repetidas} canciones enviadas ya estaban en el servidor "
                           f"(no se han duplicado): {ejemplos}", "info")
        except Exception:  # noqa: BLE001
            pass

    con = rdb.get_conn()
    try:
        for t in pendientes:
            con.execute("INSERT OR REPLACE INTO pc_enviadas(track_id, enviada_en) VALUES(?,?)",
                        (t["id"], time.strftime("%Y-%m-%dT%H:%M:%S")))
        con.commit()
    finally:
        con.close()
    return len(pendientes)


# --------------------------------------------------------------------------------------------
def _bloqueo(cfg: dict):
    """Impide que se solapen dos vueltas.

    La tarea programada de Windows vuelve a lanzar el guion cada cuarto de hora. Si una vuelta se
    alarga (una descarga lenta, un análisis de ffmpeg), sin esto habría dos procesos descargando a
    la vez, escribiendo en la misma base y mandando los mismos ficheros: trabajo duplicado y, con
    mala suerte, dos envíos del mismo tar.

    El candado caduca a las 3 horas: si un proceso murió de golpe (corte de luz, apagón), no
    queremos que el recolector del PC se quede bloqueado para siempre.
    """
    import os

    ruta = Path(cfg["datos_locales"]) / "recolector_pc.lock"
    if ruta.exists() and (time.time() - ruta.stat().st_mtime) < 3 * 3600:
        print(f"Ya hay otra vuelta en marcha (candado {ruta}). Salgo sin hacer nada.")
        return None
    ruta.write_text(str(os.getpid()), encoding="utf-8")
    return ruta


def main() -> int:
    # El registro se prepara con la configuración todavía sin leer (hace falta la carpeta de
    # datos), así que primero se lee el fichero de configuración a mano.
    try:
        bruto = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    except Exception:  # noqa: BLE001
        bruto = {}
    log = Path(bruto["datos_locales"]) / "recolector_pc.log" if bruto.get("datos_locales") else None
    preparar_salida(log)

    ap = argparse.ArgumentParser(description="Recolector del PC: descarga aquí y manda al servidor")
    ap.add_argument("--una-vuelta", action="store_true", help="una pasada y sale")
    ap.add_argument("--solo-sembrar", action="store_true", help="sólo sincroniza lo que ya hay")
    ap.add_argument("--solo-publicar", action="store_true", help="sólo manda lo pendiente")
    ap.add_argument("--minutos", type=float, default=None, help="minutos de recolección por vuelta")
    ap.add_argument("--maximo", type=int, default=None, help="canciones nuevas por vuelta")
    args = ap.parse_args()

    cfg = cargar_config()
    preparar_entorno(cfg)

    print("=" * 78)
    print(f"RECOLECTOR DEL PC · {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  música local : {cfg['musica_local']}")
    print(f"  datos locales: {cfg['datos_locales']}")
    try:
        est = estado_servidor(cfg)
        print(f"  servidor     : {cfg['api']} · ingesta {'ENCENDIDA' if est['encendida'] else 'APAGADA'}")
    except Exception as e:  # noqa: BLE001
        print(f"  AVISO: no se pudo preguntar al servidor: {e}")

    from radiov import db as rdb
    rdb.init_db()

    if args.solo_publicar:
        publicar(cfg)
        return 0

    candado = None if args.solo_sembrar else _bloqueo(cfg)
    if candado is None and not args.solo_sembrar:
        return 0
    try:
        if args.solo_sembrar:
            try:
                sembrar(cfg)
            except Exception as e:  # noqa: BLE001
                print(f"  ERROR al sembrar: {e}")
            return 0

        minutos = args.minutos if args.minutos is not None else float(cfg.get("minutos_por_vuelta", 20))
        maximo = args.maximo if args.maximo is not None else int(cfg.get("max_por_vuelta", 10))

        # Cada fase va protegida por separado y A PROPÓSITO: si una falla, las demás siguen. Antes
        # la primera siembra estaba fuera de todo try, así que un solo dato raro (un vídeo de YouTube
        # compartido por dos fichas) tumbaba el programa entero y el PC dejaba de descargar sin que
        # nadie se enterara. Lo que el usuario quiere es que siga bajando música.
        def fases() -> list:
            return [
                ("sembrar", lambda: sembrar(cfg)),
                # Lo pedido desde la app va PRIMERO: es lo que el usuario está esperando.
                ("atender peticiones", lambda: atender_peticiones(
                    cfg, maximo=int(cfg.get("peticiones_por_vuelta", 5)))),
                ("recolectar", lambda: recolectar(cfg, minutos, maximo)),
                ("completar", lambda: completar(cfg)),
                # Intros y colas: se revisan unas cuantas por vuelta. Va DESPUÉS de completar (así
                # ya tienen gain/energía y se pueden publicar) y con tope, para que no le quite tiempo
                # a lo importante, que es seguir descargando.
                ("intros y colas", lambda: revisar_extremos(
                    cfg, maximo=int(cfg.get("extremos_por_vuelta", 12)),
                    buscar_otra=int(cfg.get("versiones_limpias_por_vuelta", 2)))),
                ("publicar", lambda: publicar(cfg)),
            ]

        while True:
            print("\n--- vuelta " + time.strftime("%H:%M:%S") + " ---")
            for nombre, fn in fases():
                try:
                    fn()
                except KeyboardInterrupt:
                    print("\nParado a mano.")
                    return 0
                except Exception as e:  # noqa: BLE001
                    print(f"  ERROR en «{nombre}»: {e} (se sigue con el resto)")
            if args.una_vuelta:
                return 0
            espera = int(cfg.get("minutos_entre_vueltas", 5) * 60)
            print(f"  espero {espera // 60} min…")
            time.sleep(espera)
    finally:
        if candado is not None:
            candado.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
