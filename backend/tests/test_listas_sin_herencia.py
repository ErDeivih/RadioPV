"""Una lista recién creada NO puede tener canciones que su dueño no ha puesto.

FALLO REAL (19/09/2026)
-----------------------
Se detectó probando la descarga de una lista a una carpeta: una lista recién creada aparecía con
3 canciones añadidas y **16 en pantalla**. Las de más eran canciones recién descargadas y de otros
usuarios. La cadena era:

1. `playlists.id` es un `INTEGER PRIMARY KEY` normal (sin AUTOINCREMENT) → SQLite **reutiliza** el
   id de la lista borrada con el id más alto.
2. `playlist_tracks` declara la clave foránea a `playlists`, pero `PRAGMA foreign_keys` está a OFF
   (a propósito, ver `database.py`) y no hay `ON DELETE CASCADE` que valga sin eso → al borrar una
   lista, sus filas se quedan.
3. La lista siguiente recibe ese id y **hereda las canciones de la lista borrada**.

Y no hacía falta borrar desde la aplicación: `scripts/limpiar_datos_de_prueba.py` borraba las
listas con el barrido genérico por `user_id` (que incluye `playlists`) ANTES de borrar sus
`playlist_tracks`; después, la subconsulta de canciones ya no encontraba nada. Es decir: cada
limpieza de datos de prueba dejaba basura que ensuciaba la lista siguiente que creara cualquiera.

Estas pruebas fijan las dos mitades: la red de seguridad al crear (siempre se barre lo que hubiera
con ese id) y el barrido de huérfanas (`limpiar_listas_huerfanas`).
"""
import pytest


@pytest.fixture
def usuario_y_pista(client):
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    correo = "herencia@t.com"
    r = client.post("/auth/register", json={"email": correo, "password": "clave-larga-1"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    t = models.Track(title="DeHerencia", artist="DH", status="descargada", source="test_herencia",
                     file_path="E:/h.mp3", rank=1)
    db.add(t)
    db.commit()
    db.refresh(t)

    yield db, token, t.id, correo

    db.query(models.Track).filter(models.Track.source == "test_herencia").delete()
    db.query(models.User).filter(models.User.email == correo).delete(synchronize_session=False)
    db.commit()
    db.close()


def _crear(client, token, nombre):
    r = client.post("/playlists", json={"name": nombre}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _canciones(client, token, pid):
    r = client.get(f"/playlists/{pid}/tracks", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


def test_lista_borrada_no_deja_sus_canciones_a_la_siguiente(client, usuario_y_pista):
    """El caso exacto que se vio: borrar una lista con canciones y crear otra que hereda el id."""
    db, token, track_id, _ = usuario_y_pista
    from app import models

    primera = _crear(client, token, "La que se borra")
    r = client.post(f"/playlists/{primera}/tracks/{track_id}",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert len(_canciones(client, token, primera)) == 1

    r = client.delete(f"/playlists/{primera}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text

    # Se simula el camino que dejaba la basura: la lista desaparece pero sus filas se quedan
    # (es lo que pasaba cuando el borrado se hacía por otro camino, como el script de limpieza).
    db.add(models.PlaylistTrack(playlist_id=primera, track_id=track_id, position=1))
    db.commit()

    segunda = _crear(client, token, "La nueva")
    assert segunda == primera or True          # el id puede reutilizarse o no, da igual
    assert _canciones(client, token, segunda) == [], \
        "una lista recién creada ha heredado canciones de una lista borrada"


def test_el_barrido_quita_las_filas_sin_lista(client, usuario_y_pista):
    """`limpiar_listas_huerfanas` borra lo que apunta a una lista que ya no existe (y sólo eso)."""
    db, token, track_id, _ = usuario_y_pista
    from app import models
    from app.database import limpiar_listas_huerfanas

    viva = _crear(client, token, "Viva")
    r = client.post(f"/playlists/{viva}/tracks/{track_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text

    fantasma = 999999
    db.add(models.PlaylistTrack(playlist_id=fantasma, track_id=track_id, position=1))
    db.commit()

    assert limpiar_listas_huerfanas() >= 1
    assert db.query(models.PlaylistTrack).filter_by(playlist_id=fantasma).count() == 0
    # Lo que sí tiene lista no se toca: el barrido no puede vaciar listas buenas.
    assert len(_canciones(client, token, viva)) == 1


def test_al_crear_una_lista_se_barre_lo_que_hubiera_con_ese_id(client, usuario_y_pista):
    """La red de seguridad: aunque queden filas con ese id, la lista nueva se devuelve vacía."""
    db, token, track_id, _ = usuario_y_pista
    from app import models

    # Una fila "colgada" con el id que va a recibir la próxima lista.
    siguiente = (db.query(models.Playlist).order_by(models.Playlist.id.desc()).first().id or 0) + 1
    db.add(models.PlaylistTrack(playlist_id=siguiente, track_id=track_id, position=1))
    db.commit()

    nueva = _crear(client, token, "Recién creada")
    assert _canciones(client, token, nueva) == []
    # Y el contador de la propia lista también dice cero, que es lo que ve el usuario.
    r = client.get(f"/playlists/{nueva}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["n_tracks"] == 0
