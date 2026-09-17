"""Migration de esquema: BD antiguas (sin mixes.explicacion) deben auto-alterarse al arrancar
porque create_all() solo crea tablas que faltan, nunca columnas. Guarda a un usuario real con
una backend.db creada como parte del código."""
import os
import tempfile

from sqlalchemy import create_engine, inspect, text

from app.database import ensure_schema


def _engine(url):
    return create_engine(url)


def _engine_antiguo():
    """SQLite en archivo temporal con la tabla mixes a la ANTIGUA (sin la columna explicacion)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = _engine("sqlite:///" + path.replace("\\", "/"))
    with eng.begin() as con:
        con.execute(text(
            "CREATE TABLE mixes (id INTEGER PRIMARY KEY, user_id INTEGER, kind VARCHAR(30), "
            "seed VARCHAR(80), tracks_json TEXT, created_at DATETIME)"))
    return eng


def test_anade_columna_faltante():
    eng = _engine_antiguo()
    ensure_schema(eng)                                   # simula el arranque
    cols = {c["name"] for c in inspect(eng).get_columns("mixes")}
    assert "explicacion" in cols                          # la columna ya está


def test_idempotente():
    eng = _engine_antiguo()
    ensure_schema(eng)
    ensure_schema(eng)                                   # segunda pasada: no debe romper
    assert "explicacion" in {c["name"] for c in inspect(eng).get_columns("mixes")}


def test_tabla_nueva_ya_tiene_columna():
    """Una tabla creada por create_all (con el modelo actual) no se toca ni se duplica."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = _engine("sqlite:///" + path.replace("\\", "/"))
    from app.database import Base
    from app import models  # noqa: F401
    Base.metadata.create_all(eng)                        # crea mixes con explicacion
    ensure_schema(eng)                                   # no-error, no-op
    cols = {c["name"] for c in inspect(eng).get_columns("mixes")}
    assert "explicacion" in cols
