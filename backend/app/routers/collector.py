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
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

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
    """
    from radiov.config import load_settings
    cfg = load_settings()
    return {k: v for k, v in cfg.items() if k != "base_music_dir"}   # la ruta es de cada máquina


@router.get("/indice", summary="Qué canciones ya están (para no volver a bajarlas)",
            dependencies=[Depends(require_ingest_token)])
def indice() -> dict:
    """Lista compacta de lo que YA hay: por id de YouTube, por id de Deezer y por «artista|título».

    Se manda en tres listas planas en vez de objetos con nombre y apellidos: con 6.000 canciones
    eso es la diferencia entre 200 KB y 1 MB por vuelta, y esto se pide cada pocos minutos.
    """
    import sqlite3
    from radiov.config import DB_PATH

    con = sqlite3.connect(str(DB_PATH))
    try:
        con.row_factory = sqlite3.Row
        filas = con.execute("SELECT youtube_id, deezer_id, artist, title, status FROM tracks").fetchall()
    finally:
        con.close()

    yt, dz, claves = [], [], []
    for r in filas:
        if r["youtube_id"]:
            yt.append(r["youtube_id"])
        if r["deezer_id"]:
            dz.append(str(r["deezer_id"]))
        if r["artist"] and r["title"]:
            claves.append(f"{r['artist']}|{r['title']}")
    return {"youtube_ids": yt, "deezer_ids": dz, "claves": claves, "total": len(filas)}


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


@router.post("/importar", summary="Sube las pistas nuevas del PC al catálogo",
             dependencies=[Depends(require_ingest_token)])
def importar(datos: ImportarIn) -> dict:
    """Inserta/actualiza las pistas en `radiov.db` usando el MISMO altas que el recolector local.

    Los ficheros de audio NO vienen por aquí (son cientos de megas): se copian aparte, a la misma
    ruta relativa (`catalogada/Artista/…`), que es la que ya está guardada en `file_path`. Así el
    servidor resuelve el fichero con `resolve_music` sin tocar nada.

    Lo que sí viaja aquí es la fila entera: es lo que hace que la canción exista para el catálogo,
    con su carátula, su BPM y su ganancia ya calculados en el PC.
    """
    import sys
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    from radiov import db as rdb

    if not datos.pistas:
        return {"nuevas": 0, "actualizadas": 0, "total": 0}

    nuevas = 0
    for rec in datos.pistas:
        campos: dict[str, Any] = rec.model_dump(exclude_none=True)
        antes = rdb.get_track_id_by_artist_title(campos.get("artist", ""), campos.get("title", ""))
        try:
            rdb.add_track(campos)
        except Exception as e:  # noqa: BLE001
            rdb.log_event(f"⚠️ No se pudo importar {campos.get('artist')} - {campos.get('title')}: {e}",
                          "warning")
            continue
        if not antes:
            nuevas += 1

    rdb.log_event(f"💻 {nuevas} pistas nuevas importadas del recolector de {datos.origen}", "info")
    return {"nuevas": nuevas, "total": len(datos.pistas), "origen": datos.origen}
