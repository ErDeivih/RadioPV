"""La búsqueda tiene que ignorar tildes y mayúsculas.

En una aplicación en español la gente escribe «rosalia», «cancion» o «corazon» sin tildes. La
búsqueda era sensible a ellas: `Rosalía` encontraba 1 canción y `Rosalia` encontraba **0**, así
que para el usuario la búsqueda parecía rota (y lo era, desde su punto de vista).

Se resuelve registrando una función `sin_acentos(...)` en SQLite (ver `app/database.py`), así que
no hace falta migrar la base ni duplicar columnas.
"""
import pytest


@pytest.fixture
def catalogo(client):
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    pistas = [
        models.Track(title="DESPECHÁ", artist="Rosalía", album="MOTOMAMI", status="descargada",
                     source="test_busqueda", file_path="E:/x.mp3", rank=1),
        models.Track(title="Corazón Sin Cara", artist="Prince Royce", album="Prince Royce",
                     status="descargada", source="test_busqueda", file_path="E:/y.mp3", rank=2),
        models.Track(title="Canción Bonita", artist="Carlos Vives", album="Cumbiana",
                     status="descargada", source="test_busqueda", file_path="E:/z.mp3", rank=3),
    ]
    db.add_all(pistas)
    db.commit()
    yield db
    db.query(models.Track).filter(models.Track.source == "test_busqueda").delete()
    db.commit()
    db.close()


def _buscar(client, q):
    r = client.get("/tracks", params={"q": q, "limit": 50})
    assert r.status_code == 200, r.text
    return {t["title"] for t in r.json()}


def test_encuentra_escribiendo_sin_tildes(client, catalogo):
    assert "DESPECHÁ" in _buscar(client, "rosalia")
    assert "Corazón Sin Cara" in _buscar(client, "corazon")
    assert "Canción Bonita" in _buscar(client, "cancion")


def test_sigue_encontrando_con_tildes(client, catalogo):
    assert "DESPECHÁ" in _buscar(client, "Rosalía")
    assert "Corazón Sin Cara" in _buscar(client, "Corazón")


def test_da_igual_mayusculas_y_minusculas(client, catalogo):
    for q in ("ROSALIA", "rosalia", "RoSaLiA"):
        assert "DESPECHÁ" in _buscar(client, q), q


def test_la_funcion_de_normalizar_es_la_misma_en_python_y_en_sql():
    from app.database import normalizar_busqueda

    assert normalizar_busqueda("Rosalía") == "rosalia"
    assert normalizar_busqueda("Corazón") == "corazon"
    assert normalizar_busqueda("ÑANDÚ") == "nandu"
    assert normalizar_busqueda(None) is None
