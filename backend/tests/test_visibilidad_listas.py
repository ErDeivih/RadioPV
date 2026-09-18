"""Visibilidad de las listas: privada por defecto, compartida solo si su dueño la hace pública.

El menú de la lista ofrece «Hacer pública» / «Hacer privada» desde el principio, pero el campo
`public` NO existía en la base ni en el esquema: la petición se mandaba, el servidor la ignoraba y
la interfaz contestaba «la lista ahora es pública». Aquí se comprueba que el cambio es real y que
una lista privada no la ve nadie más.
"""
import pytest


@pytest.fixture
def cabeceras(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def otro(client):
    r = client.post("/auth/register", json={"email": "vecino-visibilidad@t.com",
                                            "password": "clave-larga-1",
                                            "display_name": "Vecino"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def lista(client, cabeceras):
    from app.database import SessionLocal
    from app import models

    t = client.post("/playlists", json={"name": "Lista con dueño"}, headers=cabeceras).json()
    pid = t["id"]
    # Una canción dentro, para poder comprobar también el listado de canciones.
    db = SessionLocal()
    try:
        db.add(models.PlaylistTrack(playlist_id=pid, track_id=1, position=1))
        db.commit()
    except Exception:  # noqa: BLE001  (si no existe la pista 1, no pasa nada)
        db.rollback()
    finally:
        db.close()

    yield pid
    client.delete(f"/playlists/{pid}", headers=cabeceras)


def test_nace_privada(client, cabeceras, lista):
    d = client.get(f"/playlists/{lista}", headers=cabeceras).json()
    assert d["public"] is False


def test_privada_no_la_ve_nadie_mas(client, cabeceras, lista, otro):
    assert client.get(f"/playlists/{lista}", headers=otro).status_code == 404
    assert client.get(f"/playlists/{lista}/tracks", headers=otro).status_code == 404
    assert client.post(f"/playlists/{lista}/tracks/1", headers=otro).status_code == 404


def test_hacerla_publica_la_comparte_de_verdad(client, cabeceras, lista, otro):
    r = client.patch(f"/playlists/{lista}", json={"public": True}, headers=cabeceras)
    assert r.status_code == 200, r.text
    assert r.json()["public"] is True

    # El vecino ahora SÍ la ve y puede leer sus canciones…
    assert client.get(f"/playlists/{lista}", headers=otro).status_code == 200
    assert client.get(f"/playlists/{lista}/tracks", headers=otro).status_code == 200
    # …pero NO puede tocarla: sigue siendo de su dueño.
    assert client.patch(f"/playlists/{lista}", json={"name": "robada"}, headers=otro).status_code == 404
    assert client.delete(f"/playlists/{lista}", headers=otro).status_code == 404
    assert client.post(f"/playlists/{lista}/tracks/2", headers=otro).status_code == 404


def test_volver_a_privada_la_esconde(client, cabeceras, lista, otro):
    client.patch(f"/playlists/{lista}", json={"public": True}, headers=cabeceras)
    assert client.get(f"/playlists/{lista}", headers=otro).status_code == 200

    r = client.patch(f"/playlists/{lista}", json={"public": False}, headers=cabeceras)
    assert r.json()["public"] is False
    assert client.get(f"/playlists/{lista}", headers=otro).status_code == 404


def test_el_cambio_se_ve_en_mi_lista_de_listas(client, cabeceras, lista):
    client.patch(f"/playlists/{lista}", json={"public": True}, headers=cabeceras)
    mias = client.get("/playlists", headers=cabeceras).json()
    assert any(p["id"] == lista and p["public"] is True for p in mias)


def test_renombrar_no_toca_la_visibilidad(client, cabeceras, lista):
    client.patch(f"/playlists/{lista}", json={"public": True}, headers=cabeceras)
    r = client.patch(f"/playlists/{lista}", json={"name": "Otro nombre"}, headers=cabeceras)
    assert r.json()["name"] == "Otro nombre"
    assert r.json()["public"] is True, "renombrar no debe volverla privada sin querer"
