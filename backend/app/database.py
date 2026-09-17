import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Por defecto SQLite local para desarrollo; con DATABASE_URL se usa Postgres/SQLAlchemy.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/backend.db")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


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
}


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
                with bind.begin() as con:
                    con.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {ddl}"))
