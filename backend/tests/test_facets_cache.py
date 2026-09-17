"""`/facets`: una sola pasada por la tabla y caché.

Antes eran cinco recorridos completos (genre, era, language, year y tags por separado) más un
bucle en Python sobre todas las etiquetas, en CADA petición, y el endpoint es público (cualquiera
puede pedirlo en bucle). El catálogo sólo cambia cuando corre la sincronización, cada 30 minutos.
"""
import time

import pytest


@pytest.fixture(autouse=True)
def limpiar_cache():
    from app.routers import facets
    facets.invalidar()
    yield
    facets.invalidar()


def _track(db, **kw):
    from app import models
    base = dict(title="F", artist="FA", genre="pop", era="20s", language="es", year=2020,
                tags="fiesta, verano", status="descargada", source="test")
    base.update(kw)
    t = models.Track(**base)
    db.add(t)
    db.commit()
    return t


def test_devuelve_los_mismos_facets_que_antes(client):
    from app.database import SessionLocal
    db = SessionLocal()
    t = _track(db, title="FacetUno", genre="techno", era="10s", language="en", year=2011,
               tags="gimnasio, fiesta")
    try:
        r = client.get("/facets")
        assert r.status_code == 200
        d = r.json()
        assert set(d) == {"genres", "eras", "languages", "years", "moods"}
        # Cada serie son parejas {value, count} ordenadas de más a menos.
        assert all(("value" in x and "count" in x) for x in d["genres"])
        counts_genre = {x["value"]: x["count"] for x in d["genres"]}
        assert counts_genre.get("techno", 0) >= 1
        counts_mood = {x["value"]: x["count"] for x in d["moods"]}
        assert counts_mood.get("gimnasio", 0) >= 1
    finally:
        db.delete(t)
        db.commit()
        db.close()


def test_la_segunda_peticion_no_recalcula(client):
    """La caché tiene que servir el mismo diccionario sin volver a contar."""
    from app.routers import facets

    llamadas = {"n": 0}
    original = facets._contar

    def contando(db):
        llamadas["n"] += 1
        return original(db)

    facets._contar = contando
    try:
        assert client.get("/facets").status_code == 200
        assert client.get("/facets").status_code == 200
        assert client.get("/facets").status_code == 200
        assert llamadas["n"] == 1, f"se recalculó {llamadas['n']} veces en vez de 1"
    finally:
        facets._contar = original


def test_la_cache_caduca(client, monkeypatch):
    from app.routers import facets

    assert client.get("/facets").status_code == 200
    monkeypatch.setattr(facets, "TTL_SEGUNDOS", 0)      # todo caduca al instante
    time.sleep(0.01)
    llamadas = {"n": 0}
    original = facets._contar

    def contando(db):
        llamadas["n"] += 1
        return original(db)

    facets._contar = contando
    try:
        client.get("/facets")
        assert llamadas["n"] == 1, "con la caché caducada tenía que recalcular"
    finally:
        facets._contar = original


def test_invalidar_refresca_los_recuentos(client):
    """Al sincronizar el catálogo se tira la caché: el recuento nuevo aparece enseguida."""
    from app.database import SessionLocal
    from app.routers import facets

    antes = {x["value"]: x["count"] for x in client.get("/facets").json()["genres"]}.get("ambient", 0)

    db = SessionLocal()
    t = _track(db, title="FacetNuevo", genre="ambient")
    try:
        # Sin invalidar, sigue sirviendo el recuento viejo (eso es la caché funcionando).
        cacheado = {x["value"]: x["count"] for x in client.get("/facets").json()["genres"]}
        assert cacheado.get("ambient", 0) == antes

        facets.invalidar()          # es lo que hace `sync_catalogo`
        fresco = {x["value"]: x["count"] for x in client.get("/facets").json()["genres"]}
        assert fresco.get("ambient", 0) == antes + 1
    finally:
        db.delete(t)
        db.commit()
        db.close()
        facets.invalidar()
