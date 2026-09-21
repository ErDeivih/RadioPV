"""«Tech house y guaracha»: la lista de la música que el usuario pidió por su nombre.

Pidió expresamente: «me gustan los tech house remix y este tipo de canciones hechas por gente, por
ejemplo estoy viendo un tal Pomata en spotify… con bass, en español o inglés o mezcla, usando una o
varias canciones originales». Hasta ahora esa música estaba en el catálogo pero **no había forma de
ponerla a sonar**: se comprueba aquí que la lista la recoge entera, en el orden correcto y sin colar
lo que no es (ni portugués, ni pop normal).
"""
from app.database import SessionLocal
from app import models
from app.workers import rebuild_remixes


def _pista(db, tid_titulo, artista, **kw):
    t = models.Track(title=tid_titulo, artist=artista, status="descargada",
                     source="test_techhouse", file_path=f"E:/{tid_titulo}.mp3", **kw)
    db.add(t)
    db.commit()
    return t


def _lista(db, nombre):
    pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
    assert pl, f"no se creó la lista «{nombre}»"
    filas = (db.query(models.PlaylistTrack)
             .filter_by(playlist_id=pl.id).order_by(models.PlaylistTrack.position).all())
    return [f.track_id for f in filas]


def test_lista_tech_house(client):
    db = SessionLocal()
    try:
        # Lo que TIENE que entrar: el género lo dice el título (caso normal en YouTube)…
        por_titulo = _pista(db, "El Farsante (Tech House Remix)", "Bad Bunny", genre="other", rank=500)
        guaracha = _pista(db, "Tití Me Preguntó (Guaracha)", "Tomi DJ", genre="other", rank=300)
        # …el género ya viene en la ficha (lo puso el recolector con las semillas nuevas)…
        por_ficha = _pista(db, "Drugs From Amsterdam", "Mau P", genre="techhouse", rank=900)
        # …y el artista sin ninguna pista en el título (el caso que fallaba: salía «other»).
        por_artista = _pista(db, "Una Cualquiera (Extended Mix)", "Pomata", genre="other", rank=100)

        # Lo que NO tiene que entrar.
        pop = _pista(db, "Levitating", "Dua Lipa", genre="pop", rank=9999)
        portugues = _pista(db, "Baile de Favela (Tech House Remix)", "MC João",
                           genre="other", language="pt", rank=9998)
        otra_sesion = _pista(db, "Sesión de cumbia 2025", "Dj RuLoX", genre="cumbia", rank=9997)

        # Pistas para las OTRAS dos listas: así se comprueba que añadir la tercera no las rompió
        # (una sola llamada a `rebuild_remixes` genera las tres).
        mashup = _pista(db, "Tití Me Preguntó Mashup Safaera", "DJ Prueba", genre="other",
                        duration=240, rank=60)
        sesion = _pista(db, "Tech House DJ Set 2025", "DJ Prueba", genre="techhouse",
                        duration=3600, rank=40)

        rebuild_remixes(db)

        dentro = _lista(db, "Tech house y guaracha")
        for t in (por_titulo, guaracha, por_ficha, por_artista):
            assert t.id in dentro, f"«{t.title}» ({t.artist}) debería estar en la lista"
        for t in (pop, portugues, otra_sesion, mashup):
            assert t.id not in dentro, f"«{t.title}» ({t.artist}) NO debería estar en la lista"
        # Ordenado por popularidad: primero lo que más suena (Mau P 900 > Bad Bunny 500 > …).
        assert dentro.index(por_ficha.id) < dentro.index(por_titulo.id) < dentro.index(guaracha.id)

        # Una sesión de tech house es de las dos cosas, y en las dos sale.
        assert sesion.id in dentro
        assert sesion.id in _lista(db, "Sesiones de DJ")
        # Y las otras dos listas siguen teniendo lo suyo (no se rompió nada al añadir la tercera).
        assert mashup.id in _lista(db, "Mashups y remixes")

        # «Club y festival»: la electrónica de pista (dance/house/electro/techno) más el tech house,
        # que es el terreno del perfil de electrónica que pidió el usuario. Una sesión de tech house
        # cuenta por partida doble (duración → sesiones; género → club), y eso es correcto.
        club = _lista(db, "Club y festival")
        assert por_ficha.id in club, "el tech house también es música de club"
        assert sesion.id in club, "una sesión de tech house es música de club"
        assert pop.id not in club, "una canción de pop no es música de pista"
        assert portugues.id not in club
    finally:
        db.query(models.Track).filter(models.Track.source == "test_techhouse").delete()
        for nombre in ("Tech house y guaracha", "Mashups y remixes", "Sesiones de DJ",
                       "Club y festival"):
            pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
            if pl:
                db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
                db.delete(pl)
        db.commit()
        db.close()
