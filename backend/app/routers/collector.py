"""Sincronización con el recolector del PC (`/collector/...`).

POR QUÉ EXISTE
--------------
El recolector (buscar en YouTube, descargar, etiquetar, analizar) es lo que más CPU y disco come
del servidor, y el servidor es un portátil de 4 GB sin swap. En el PC de casa, en cambio, sobra
máquina — y está encendido igualmente.

Este módulo es la otra mitad del reparto: el PC hace el trabajo pesado y el servidor se queda con
lo que sólo él puede hacer (servir la aplicación, generar listas y mixes, guardar la biblioteca).
Aquí van las tres piezas que el PC necesita:

    GET  /collector/ajustes   → la configuración del recolector (semillas, política, vetos)
    GET  /collector/indice    → qué canciones YA están (para no volver a bajarlas)
    POST /collector/importar  → sube las pistas nuevas (los ficheros van por otro camino)

AUTENTICACIÓN
-------------
Con un **token de máquina** (`RADIOPV_INGEST_TOKEN`), no con usuario y contraseña: el PC no es
una persona y no puede tener la contraseña del administrador guardada en un fichero. Se compara
con `secrets.compare_digest` (comparación en tiempo constante, para no ir soltando pistas por el
tiempo que tarda en fallar). Si la variable no está puesta, estas rutas devuelven **503**: es
mejor que digan que están apagadas a que acepten cualquier cosa.
"""
import os
import secrets
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from .. import models

router = APIRouter(prefix="/collector", tags=["collector"])


def _token_esperado() -> Optional[str]:
    return os.environ.get("RADIOPV_INGEST_TOKEN") or None


def require_ingest_token(x_ingest_token: Optional[str] = Header(None)) -> None:
    esperado = _token_esperado()
    if not esperado:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "La ingesta desde otro equipo está apagada en este servidor "
                            "(falta RADIOPV_INGEST_TOKEN)")
    if not x_ingest_token or not secrets.compare_digest(x_ingest_token, esperado):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de recolección incorrecto")


@router.get("/estado", summary="¿Está encendida la ingesta desde otro equipo?")
def estado() -> dict:
    """Público a propósito: sólo dice si está encendida, no comprueba el token.

    Sirve para que el PC pueda avisar «el servidor no acepta mis envíos» sin tener que intentar
    subir nada y quedarse con un error raro.
    """
    return {"encendida": _token_esperado() is not None,
            "ruta_musica": os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music"}


@router.get("/ajustes", summary="Configuración del recolector (semillas, política, vetos)",
            dependencies=[Depends(require_ingest_token)])
def ajustes() -> dict:
    """La configuración que manda: el PC recolecta con las MISMAS reglas que el servidor.

    Sin esto, el PC tendría su propia copia de las semillas y de la política de idiomas, y con el
    tiempo las dos listas se separarían: acabaría bajando música que el servidor ya no quiere.

    Lo que NO viaja son las **rutas**: en el servidor la música está en `/music` y en el PC en
    `E:/MusicaRadioPV`. Si se mandaran, el PC escribiría en `F:\\music\\…` (así se resuelve `/music`
    en Windows) y los ficheros acabarían fuera de su carpeta sin que nadie se enterara.
    """
    from radiov.config import load_settings

    RUTAS_DE_CADA_MAQUINA = ("base_music_dir", "download_dir", "catalog_dir", "playlist_dir")
    cfg = load_settings()
    return {k: v for k, v in cfg.items() if k not in RUTAS_DE_CADA_MAQUINA}


@router.get("/indice", summary="Qué canciones ya están (para no volver a bajarlas)",
            dependencies=[Depends(require_ingest_token)])
def indice(desde_id: int = Query(0, ge=0, description="devuelve sólo las canciones con id mayor"),
           limite: Optional[int] = Query(None, ge=1, le=20000,
                                         description="tope de filas (por seguridad)")) -> dict:
    """Lo que YA hay, con sus identificadores.

    Se manda una lista de listas (`[id, título, artista, id_youtube, id_deezer]`) en vez de objetos
    con nombres de campo: con 6.000 canciones eso es la mitad de bytes, y esto se pide cada pocos
    minutos.

    **Los identificadores son imprescindibles**, no un extra: el recolector comprueba antes de
    bajar nada si ese vídeo de YouTube ya está (`pista_existente`), y sin el id el PC no puede
    saberlo. Cuando se mandaban sólo «artista + título», el PC volvía a descargar canciones que ya
    tenía —con otro nombre de artista, o de otro vídeo— y las volvía a enviar. Se descubrió comparando
    los ficheros de las dos máquinas: los del servidor eran más antiguos que los del PC, que es
    exactamente «la misma canción bajada dos veces».

    POR QUÉ SE PUEDE PEDIR SÓLO LO NUEVO (`desde_id`)
    ------------------------------------------------
    Antes había que traerse las 6.000 filas enteras en cada vuelta para saber si había algo nuevo, y
    el PC hace una vuelta cada 15 minutos: son ~200 KB y un recorrido completo de la tabla 96 veces al
    día, para descubrir casi siempre que no ha cambiado nada. Con `desde_id` (el `max_id` que el PC
    guardó la última vez) la consulta es «lo que se ha añadido desde entonces»: unas pocas filas, con
    el índice por id, y el servidor no se entera.
    """
    import sqlite3
    from radiov.config import DB_PATH

    con = sqlite3.connect(str(DB_PATH))
    try:
        con.row_factory = sqlite3.Row
        total = con.execute("SELECT COUNT(*) n FROM tracks").fetchone()["n"]
        max_id = con.execute("SELECT COALESCE(MAX(id), 0) m FROM tracks").fetchone()["m"]
        sql = ("SELECT id, title, artist, youtube_id, deezer_id FROM tracks"
               " WHERE id > ? ORDER BY id")
        args: tuple = (desde_id,)
        if limite:
            sql += " LIMIT ?"
            args += (limite,)
        filas = con.execute(sql, args).fetchall()
    finally:
        con.close()

    pistas = [[r["id"], r["title"] or "", r["artist"] or "", r["youtube_id"] or "",
               str(r["deezer_id"] or "")]
              for r in filas if r["title"] and r["artist"]]
    return {"total": total, "max_id": max_id, "desde_id": desde_id,
            "nuevas": len(pistas), "pistas": pistas}


class Rec(BaseModel):
    """Una pista descargada en el PC. Se aceptan los campos que llena el recolector."""

    model_config = {"extra": "allow"}

    title: str
    artist: str
    file_path: Optional[str] = None
    duration: Optional[float] = None
    status: Optional[str] = None
    youtube_id: Optional[str] = None
    deezer_id: Optional[str] = None


class ImportarIn(BaseModel):
    pistas: list[Rec] = Field(default_factory=list)
    origen: str = "pc"


class PeticionEstado(BaseModel):
    """Lo que el PC contesta sobre una canción pedida desde la app."""

    estado: Literal["descargada", "fallida"]
    detalle: Optional[str] = None


@router.get("/peticiones", summary="Canciones pedidas desde la app y aún sin resolver",
            dependencies=[Depends(require_ingest_token)])
def peticiones(limite: int = Query(20, ge=1, le=200)) -> dict:
    """Las peticiones pendientes, para que el PC las descargue.

    La tabla `requests` existía desde el principio y la app podía crear peticiones… pero **no las
    consumía nadie**: se quedaban en `pendiente` para siempre (había 21 esperando). El recolector
    se había mudado al PC, así que es el PC quien tiene que recogerlas, descargarlas y contestar.
    """
    import sys
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        filas = (db.query(models.Request)
                 .filter(models.Request.status == "pendiente")
                 .order_by(models.Request.created_at.asc())
                 .limit(limite).all())
        return {"total": len(filas),
                "peticiones": [{"id": r.id, "text": r.text,
                                # El vídeo elegido a mano, si lo hay: el PC baja ESE y no busca.
                                "youtube_id": r.youtube_id,
                                "duration": r.duration,
                                "pedida": r.created_at.isoformat(timespec="seconds")
                                if r.created_at else None} for r in filas]}
    finally:
        db.close()


@router.post("/peticiones/{peticion_id}", summary="El PC dice qué ha pasado con una petición",
             dependencies=[Depends(require_ingest_token)])
def resolver_peticion(peticion_id: int, datos: PeticionEstado) -> dict:
    """Marca la petición como resuelta (descargada) o como no encontrada (fallida).

    Se contesta siempre, incluso cuando no se encuentra: si se dejara en `pendiente`, el PC volvería
    a intentarlo en cada vuelta y la página del usuario se quedaría en «en cola» para siempre, que
    es justo lo que pasaba antes.
    """
    import sys
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        r = db.query(models.Request).filter_by(id=peticion_id).first()
        if not r:
            raise HTTPException(404, "Petición no encontrada")
        r.status = datos.estado
        db.commit()
        return {"ok": True, "estado": r.status, "texto": r.text}
    finally:
        db.close()


@router.post("/importar", summary="Sube las pistas nuevas del PC al catálogo",
             dependencies=[Depends(require_ingest_token)])
def importar(datos: ImportarIn) -> dict:
    """Inserta/actualiza las pistas en `radiov.db` usando el MISMO altas que el recolector local.

    Los ficheros de audio NO vienen por aquí (son cientos de megas): se copian aparte, a la misma
    ruta relativa (`catalogada/Artista/…`), que es la que ya está guardada en `file_path`. Así el
    servidor resuelve el fichero con `resolve_music` sin tocar nada.

    Lo que sí viaja aquí es la fila entera: es lo que hace que la canción exista para el catálogo,
    con su carátula, su BPM y su ganancia ya calculados en el PC.

    NO SE DUPLICA LO QUE YA ESTÁ
    ----------------------------
    Aquí estaba el agujero: se insertaba mirando sólo «artista + título» **exactos**, así que la
    misma canción con otro nombre («(Official Video)», «(feat. …)») o **desde otro vídeo** entraba
    como una ficha nueva. La biblioteca acabó con dos, tres y hasta cuatro fichas del mismo tema; una
    de ellas apuntando a un fichero que ya no existía, que es lo que hace que una canción aparezca en
    la aplicación y no suene.

    Ahora cada pista que llega se resuelve con `pista_existente` (vídeo → Deezer → clave
    normalizada) y, si ya está, **no se inserta**: se rellenan sólo sus huecos y se contesta
    `repetida`, para que el PC lo sepa y no lo reintente. Y esto no le cuesta ni una petición más al
    servidor: el PC ya mandaba este lote; sólo se mira antes de escribir.
    """
    import sys
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    from radiov import db as rdb

    if not datos.pistas:
        return {"nuevas": 0, "repetidas": 0, "total": 0, "repetidas_detalle": []}

    # Las claves de toda la biblioteca, de UNA vez: comprobar cada pista del lote contra la base una
    # por una serían decenas de consultas por vuelta para nada.
    claves = rdb.indice_de_claves()

    nuevas = 0
    repetidas: list[dict] = []
    for rec in datos.pistas:
        campos: dict[str, Any] = rec.model_dump(exclude_none=True)
        ya = rdb.pista_existente(youtube_id=campos.get("youtube_id"),
                                 deezer_id=campos.get("deezer_id"),
                                 artist=campos.get("artist", ""),
                                 title=campos.get("title", ""),
                                 claves=claves)
        if ya:
            rellenos = rdb.rellenar_huecos(ya, campos)
            repetidas.append({"id": ya, "artist": campos.get("artist"),
                              "title": campos.get("title"),
                              "youtube_id": campos.get("youtube_id"),
                              "rellenos": rellenos})
            continue
        try:
            nuevo_id = rdb.add_track(campos)
        except Exception as e:  # noqa: BLE001
            rdb.log_event(f"⚠️ No se pudo importar {campos.get('artist')} - {campos.get('title')}: {e}",
                          "warning")
            continue
        nuevas += 1
        # La clave recién insertada entra en el diccionario en memoria: si el mismo lote trae dos
        # veces la misma canción (pasa: dos vídeos del mismo tema), la segunda se reconoce en vez de
        # entrar como ficha nueva.
        claves[rdb.clave_cancion(campos.get("artist", ""), campos.get("title", ""))] = nuevo_id

    rdb.log_event(f"💻 Importadas del recolector de {datos.origen}: {nuevas} nuevas, "
                  f"{len(repetidas)} que ya estaban (no se duplican)", "info")
    return {"nuevas": nuevas, "repetidas": len(repetidas), "total": nuevas + len(repetidas),
            "repetidas_detalle": repetidas}
