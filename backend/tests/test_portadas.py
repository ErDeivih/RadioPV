"""Portadas de lista (PUT/DELETE /playlists/{id}/cover).

Antes de esto la interfaz ofrecía «elegir foto» y la función del servicio era un
`return { data: true }`: no llamaba a la API. El usuario elegía una foto y no pasaba nada.
Aquí se comprueba que la subida es real, que se ve, que se puede quitar, y que no se puede
tocar la lista de otra persona.

Se ejecuta con el `conftest.py` de la carpeta: `MEDIA_ROOT` apunta a una carpeta temporal
(`_test_media`), así que ningún fichero de prueba acaba en los datos de verdad.
"""
import pytest

# Firmas reales mínimas: lo que valida el servidor son los primeros bytes del fichero, no el
# `content-type` que declare la petición.
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"\xff\xd9"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489")


@pytest.fixture
def cabeceras(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def lista(client, cabeceras):
    r = client.post("/playlists", json={"name": "Con portada"}, headers=cabeceras)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    client.delete(f"/playlists/{pid}", headers=cabeceras)


def subir(client, cabeceras, pid, datos=JPEG, nombre="p.jpg", tipo="image/jpeg"):
    return client.put(f"/playlists/{pid}/cover", headers=cabeceras,
                      files={"file": (nombre, datos, tipo)})


def test_subir_portada_y_verla(client, cabeceras, lista):
    r = subir(client, cabeceras, lista)
    assert r.status_code == 200, r.text
    portada = r.json()["cover"]
    assert portada and portada.startswith("/media/covers/playlist-"), portada

    # La imagen se sirve de verdad por la ruta que devuelve la API.
    img = client.get(portada)
    assert img.status_code == 200, img.text
    assert img.content == JPEG

    # Y la lista la anuncia (es lo que pinta el móvil).
    assert client.get(f"/playlists/{lista}", headers=cabeceras).json()["cover"] == portada
    mias = client.get("/playlists", headers=cabeceras).json()
    assert any(p["id"] == lista and p["cover"] == portada for p in mias)


def test_acepta_png(client, cabeceras, lista):
    r = subir(client, cabeceras, lista, datos=PNG, nombre="p.png", tipo="image/png")
    assert r.status_code == 200, r.text
    assert r.json()["cover"].endswith(".png")


def test_reemplazar_borra_la_anterior(client, cabeceras, lista):
    vieja = subir(client, cabeceras, lista).json()["cover"]
    nueva = subir(client, cabeceras, lista).json()["cover"]
    assert vieja != nueva
    assert client.get(nueva).status_code == 200
    # El fichero viejo no se queda ocupando sitio en el disco.
    assert client.get(vieja).status_code == 404


@pytest.mark.parametrize("datos,tipo", [
    (b"esto no es una imagen", "image/jpeg"),          # content-type mentiroso
    (b"<html><body>hola</body></html>", "image/png"),
    (b"", "image/jpeg"),                               # fichero vacío
])
def test_rechaza_lo_que_no_es_imagen(client, cabeceras, lista, datos, tipo):
    r = subir(client, cabeceras, lista, datos=datos, tipo=tipo)
    assert r.status_code in (400, 415), f"{r.status_code} {r.text}"
    assert client.get(f"/playlists/{lista}", headers=cabeceras).json()["cover"] is None


def test_rechaza_imagen_gigante(client, cabeceras, lista):
    grande = JPEG + b"\x00" * (4 * 1024 * 1024 + 10)
    r = subir(client, cabeceras, lista, datos=grande)
    assert r.status_code == 413, r.text


def test_quitar_portada(client, cabeceras, lista):
    portada = subir(client, cabeceras, lista).json()["cover"]
    r = client.delete(f"/playlists/{lista}/cover", headers=cabeceras)
    assert r.status_code == 200, r.text
    assert r.json()["cover"] is None
    assert client.get(portada).status_code == 404
    # Quitarla dos veces no es un error: es lo que quiere decir «no tiene portada».
    assert client.delete(f"/playlists/{lista}/cover", headers=cabeceras).status_code == 200


def test_borrar_la_lista_borra_su_portada(client, cabeceras, lista):
    portada = subir(client, cabeceras, lista).json()["cover"]
    assert client.delete(f"/playlists/{lista}", headers=cabeceras).status_code == 200
    assert client.get(portada).status_code == 404


def test_no_se_puede_tocar_la_lista_de_otro(client, cabeceras, lista):
    r = client.post("/auth/register", json={"email": "otro-portadas@t.com",
                                            "password": "clave-larga-1",
                                            "display_name": "Otro"})
    assert r.status_code == 200, r.text
    ajeno = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert subir(client, ajeno, lista).status_code == 404
    assert client.delete(f"/playlists/{lista}/cover", headers=ajeno).status_code == 404


def test_las_listas_del_sistema_no_llevan_portada_de_usuario(client, cabeceras):
    """Las listas que genera la aplicación no tienen dueño: nadie puede cambiarles la portada."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        pl = models.Playlist(user_id=None, name="Trending de prueba", type="system")
        db.add(pl)
        db.commit()
        pid = pl.id
    finally:
        db.close()

    try:
        assert subir(client, cabeceras, pid).status_code == 404
    finally:
        db = SessionLocal()
        try:
            db.query(models.Playlist).filter_by(id=pid).delete()
            db.commit()
        finally:
            db.close()


def test_con_una_sesion_sin_token_no_se_puede(client, lista):
    r = client.put(f"/playlists/{lista}/cover",
                   files={"file": ("p.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 401
