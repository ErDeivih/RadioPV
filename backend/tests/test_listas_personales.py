"""Las listas generadas PARA UNA PERSONA no pueden verse desde otra cuenta.

Contexto del fallo (18/09/2026): `rebuild_home_tops` creaba «Top {id_del_usuario}» y
«Subiendo {id_del_usuario}» con `user_id=None`, o sea **sin dueño**. Consecuencias:

* aparecían en `/playlists/system`, que es la fila de listas destacadas que ve todo el mundo, con
  un nombre que parecía un error de programación («Top 12»);
* al abrirlas desde otra cuenta daban 404 (la comprobación de propiedad las oculta), así que eran
  una fila de enlaces rotos.

Ahora llevan dueño y nombre de verdad («Tus más escuchadas», «Descubrimientos de la semana») y
`/playlists/system` sólo devuelve las que la aplicación genera para todos.
"""
import pytest


@pytest.fixture
def dos_usuarios(client):
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    emails = ("personales_a@t.com", "personales_b@t.com")
    tokens = []
    for e in emails:
        r = client.post("/auth/register", json={"email": e, "password": "clave-larga-1"})
        assert r.status_code == 200, r.text
        tokens.append(r.json()["access_token"])

    t = models.Track(title="DeLista", artist="DL", status="descargada", source="test_pers",
                     file_path="E:/x.mp3", rank=1)
    db.add(t)
    db.commit()
    db.refresh(t)

    # Una lista PERSONAL del usuario A, como las que genera el worker.
    a = db.query(models.User).filter_by(email=emails[0]).first()
    pl = models.Playlist(user_id=a.id, name="Tus más escuchadas", type="system")
    db.add(pl)
    db.commit()
    db.refresh(pl)
    db.add(models.PlaylistTrack(playlist_id=pl.id, track_id=t.id, position=1))
    db.commit()

    yield db, tokens, pl.id, t.id, emails

    db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
    db.delete(pl)
    db.query(models.Track).filter(models.Track.source == "test_pers").delete()
    db.query(models.User).filter(models.User.email.in_(emails)).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_la_lista_personal_no_sale_en_las_destacadas(client, dos_usuarios):
    _db, tokens, pl_id, _t, _emails = dos_usuarios
    # Se consulta COMO EL OTRO USUARIO: es el caso que fallaba (veía la lista ajena).
    r = client.get("/playlists/system", headers={"Authorization": f"Bearer {tokens[1]}"})
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert pl_id not in ids, "una lista personal apareció en las listas para todos"


def test_la_lista_personal_aparece_en_las_del_usuario(client, dos_usuarios):
    _db, tokens, pl_id, _t, _emails = dos_usuarios
    r = client.get("/playlists", headers={"Authorization": f"Bearer {tokens[0]}"})
    assert r.status_code == 200
    assert pl_id in [p["id"] for p in r.json()]


def test_otro_usuario_no_puede_abrir_la_lista_personal(client, dos_usuarios):
    _db, tokens, pl_id, _t, _emails = dos_usuarios
    h_b = {"Authorization": f"Bearer {tokens[1]}"}
    assert client.get(f"/playlists/{pl_id}", headers=h_b).status_code == 404
    assert client.get(f"/playlists/{pl_id}/tracks", headers=h_b).status_code == 404
    # Y el dueño sí
    h_a = {"Authorization": f"Bearer {tokens[0]}"}
    assert client.get(f"/playlists/{pl_id}", headers=h_a).status_code == 200
