import os
import unicodedata
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Por defecto SQLite local para desarrollo; con DATABASE_URL se usa Postgres/SQLAlchemy.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/backend.db")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

_ES_SQLITE = DATABASE_URL.startswith("sqlite")


def normalizar_busqueda(texto: str | None) -> str | None:
    """Pasa a minúsculas y quita los acentos, para buscar como escribe la gente.

    En una aplicación en español la gente escribe «rosalia», «cancion» o «corazon» sin tildes, y
    la búsqueda era sensible a ellas: `Rosalía` encontraba 1 canción y `Rosalia` encontraba 0.
    """
    if texto is None:
        return None
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", str(texto))
                         if unicodedata.category(c) != "Mn")
    return sin_tildes.lower()


# ¿Se puede usar `sin_acentos(...)` dentro de una consulta SQL? Sólo en SQLite, que es donde se
# registra la función más abajo. En otro motor (Postgres) se buscaría sin normalizar.
HAY_SIN_ACENTOS = _ES_SQLITE


if _ES_SQLITE:
    @event.listens_for(engine, "connect")
    def _configurar_sqlite(dbapi_conn, _registro):  # noqa: ANN001
        """Ajustes de SQLite que faltaban, y que importan porque hay DOS procesos escribiendo.

        La API y el worker abren la misma base a la vez. Sin esto:
          · journal_mode por defecto (rollback) bloquea a los lectores mientras alguien escribe
            → «database is locked» en cuanto coinciden una sincronización y una petición;
          · sin `busy_timeout`, SQLite devuelve el error AL INSTANTE en vez de esperar un poco.
        El módulo del colector (`radiov/db.py`) ya lo hacía así; la base de la API se había
        quedado sin ello.

        NO se activa `PRAGMA foreign_keys=ON` a propósito: al probarlo, flujos que hoy funcionan
        fallan con «FOREIGN KEY constraint failed» (hay filas históricas que apuntan a pistas que
        ya no están, por ejemplo reproducciones de canciones retiradas). Antes de activarlo hay
        que limpiar esos datos; mientras tanto, activarlo rompería escrituras reales.
        """
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")      # lectores y escritor a la vez
            cursor.execute("PRAGMA busy_timeout=5000")     # espera 5 s antes de rendirse
            cursor.execute("PRAGMA synchronous=NORMAL")    # en WAL es seguro y más rápido
        finally:
            cursor.close()
        # `sin_acentos(...)` para poder buscar ignorando tildes desde SQL (ver el router /tracks).
        dbapi_conn.create_function("sin_acentos", 1, normalizar_busqueda)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columnas que algún día se añadieron a los modelos y las bases antiguas (creadas antes de
# ese cambio) aún no tienen. create_all() solo crea tablas que faltan, NUNCA añade columnas;
# por eso hay que alterarlas a mano. Idempotente: se ejecuta en cada arranque.
_MIGRACIONES_COLUMNAS = {
    "mixes": [
        ("explicacion", "TEXT"),      # R5 · motivo de la mezcla
    ],
    "tracks": [
        ("youtube_id", "VARCHAR(40)"),
        ("yt_views", "BIGINT"),
        ("yt_likes", "BIGINT"),
        ("popularidad", "FLOAT"),
    ],
    "playlists": [
        ("cover_path", "TEXT"),       # portada propia de la lista
        ("public", "BOOLEAN DEFAULT 0"),
    ],
    "requests": [
        # El vídeo exacto elegido en la página de pedir canciones (ver models.Request).
        ("youtube_id", "VARCHAR(40)"),
        ("duration", "FLOAT"),
    ],
}


# Índices que faltaban. `tracks.status` se filtra en casi TODAS las consultas («solo las
# descargadas»), y sin índice eso es un recorrido completo de la tabla en cada petición; en un
# HDD y con 5000 canciones se nota. `album` y `rank` se filtran/ordenan a menudo.
_MIGRACIONES_INDICES = {
    "tracks": [
        ("ix_tracks_status", "status"),
        ("ix_tracks_status_id", "status, id"),
        ("ix_tracks_album", "album"),
        ("ix_tracks_rank", "rank"),
        ("ix_tracks_popularidad", "popularidad"),
    ],
    "plays": [
        ("ix_plays_user_track", "user_id, track_id"),
    ],
}


def limpiar_listas_huerfanas(bind=None) -> int:
    """Borra filas de `playlist_tracks` cuya lista ya no existe. Devuelve cuántas borró.

    POR QUÉ HACE FALTA
    ------------------
    `playlists.id` es un `INTEGER PRIMARY KEY` normal, y SQLite reutiliza esos ids: si se borra la
    lista con el id más alto, la siguiente lista que se cree recibe ESE id. Si al borrar la lista
    se quedaron sus filas en `playlist_tracks` (y se quedaban: la clave foránea está declarada
    pero `PRAGMA foreign_keys` está a OFF, así que no borra nada en cascada), la lista nueva
    **nace con las canciones de la lista borrada**. Se vio de verdad: una lista recién creada
    aparecía con 3 canciones puestas y 16 en pantalla, y las de más eran de listas de otros
    usuarios ya borradas.

    Se ejecuta al arrancar (API y worker) para que la base se cure sola: cualquier camino que en
    el futuro olvide borrar estas filas queda corregido en el siguiente arranque.
    """
    if bind is None:
        bind = engine
    try:
        with bind.begin() as con:
            cur = con.execute(text(
                "DELETE FROM playlist_tracks WHERE playlist_id IS NULL"
                " OR playlist_id NOT IN (SELECT id FROM playlists)"))
            return cur.rowcount or 0
    except Exception:  # noqa: BLE001
        return 0


def ensure_schema(bind=None) -> None:
    """Añade a las tablas existentes las columnas que el modelo ya declara pero la BD de un
    usuario anterior no tiene. Llámalo después de Base.metadata.create_all(). No destructivo."""
    if bind is None:
        bind = engine
    insp = inspect(bind)
    for tabla, columnas in _MIGRACIONES_COLUMNAS.items():
        if not insp.has_table(tabla):
            continue
        existentes = {c["name"] for c in insp.get_columns(tabla)}
        for nombre, ddl in columnas:
            if nombre not in existentes:
                try:
                    with bind.begin() as con:
                        con.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {ddl}"))
                except Exception:  # noqa: BLE001
                    # La API y el worker arrancan casi a la vez y los dos llaman aquí: el segundo
                    # recibía «duplicate column name» y no arrancaba. Si ya está, es que lo hizo
                    # el otro proceso, que es justo lo que queríamos.
                    pass

    for tabla, indices in _MIGRACIONES_INDICES.items():
        if not insp.has_table(tabla):
            continue
        for nombre, columnas in indices:
            try:
                with bind.begin() as con:
                    con.execute(text(f"CREATE INDEX IF NOT EXISTS {nombre} ON {tabla} ({columnas})"))
            except Exception:  # noqa: BLE001
                pass

    # Al final, y después de que existan todas las columnas: quitar la basura que hace que una
    # lista nueva herede canciones de una lista borrada (ver `limpiar_listas_huerfanas`).
    limpiar_listas_huerfanas(bind)
