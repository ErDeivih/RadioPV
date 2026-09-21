"""EDM, car bass y música de graves: los géneros que el usuario pidió por su nombre.

Pidió: «también algún género de car bass, edm, etc, revisa por si no estuviera ya». No estaban:
`edm` y `trance` eran palabras sueltas dentro de `dance`/`electro` (así que un «EDM Festival Mix»
acababa en `dance` y no había ni género ni lista propios), y «car bass» —el nombre que tiene en
YouTube la música hecha para el coche: graves subidos, «bass boosted», pruebas de subwoofer— no
aparecía en ninguna parte.

Se comprueba aquí (a) que el título basta para clasificar cada uno de esos géneros, (b) que las
palabras nuevas no se roban entre ellas, (c) que hay semillas de descarga para todos y (d) que la
lista «Bass y car music» recoge dubstep, drum and bass y car bass, sin colar lo que no es.
"""
from app.database import SessionLocal
from app import models
from app.workers import rebuild_remixes

NUEVOS = ("edm", "carbass", "dubstep", "dnb", "hardstyle", "trance")


def test_el_titulo_basta_para_clasificar_los_generos_nuevos():
    """`guess_genre` con títulos reales de YouTube: cada uno a su género, no todos a 'other'."""
    from radiov.catalog import guess_genre

    casos = {
        "EDM Festival Mix 2025": "edm",
        "Martin Garrix - Animals (Big Room)": "edm",
        "Car Bass Boosted - Best Car Music 2025": "carbass",
        "Bass Boosted Car Audio Test": "carbass",
        "Skrillex - Scary Monsters (Dubstep)": "dubstep",
        "Riddim Dubstep Mix": "dubstep",
        "Liquid Drum and Bass Mix": "dnb",
        "Neurofunk DnB Session": "dnb",
        "Hardstyle Top 100 2025": "hardstyle",
        "Rawstyle Uptempo Mix": "hardstyle",
        "Uplifting Trance Classics": "trance",
        "Psytrance Set 2025": "trance",
    }
    for titulo, esperado in casos.items():
        assert guess_genre(titulo, "") == esperado, f"«{titulo}» → {guess_genre(titulo, '')}"


def test_las_palabras_nuevas_no_se_roban_entre_ellas():
    """Los géneros que ya existían siguen clasificándose igual: no se han pisado al añadir estos."""
    from radiov.catalog import guess_genre

    assert guess_genre("El Farsante (Tech House Remix)", "Bad Bunny") == "techhouse"
    assert guess_genre("Tech House Bootleg", "") == "techhouse"
    assert guess_genre("Bailando (Bachata)", "Romeo Santos") == "bachata"
    assert guess_genre("Corridos Tumbados Mix", "") == "corridos"
    assert guess_genre("Balada romántica", "") == "ballad"
    # Y el EDM ya no se queda en `dance`: tiene género propio.
    assert guess_genre("Dance Monkey", "") != "edm"


def test_hay_semillas_de_descarga_para_cada_genero_nuevo():
    """Sin semillas, el género existe en el vocabulario pero no llega música nunca."""
    from radiov.config import DEFAULT_SETTINGS

    semillas = DEFAULT_SETTINGS["agent_seeds"]
    for genero in NUEVOS:
        cuantas = [s for s in semillas if s.get("genre") == genero]
        assert cuantas, f"el género «{genero}» no tiene ninguna semilla de descarga"
    # Y las palabras del vocabulario están declaradas (si no, el título no clasificaría).
    for genero in NUEVOS:
        assert DEFAULT_SETTINGS["genre_keywords"].get(genero), f"«{genero}» sin palabras clave"


def test_lista_bass_y_car_music(client):
    """«Bass y car music»: los tres géneros de graves, ordenados por popularidad y sin colar pop."""
    db = SessionLocal()
    try:
        car = models.Track(title="Car Bass Boosted 2025", artist="Bass Nation",
                           status="descargada", source="test_bass", file_path="E:/a.mp3",
                           genre="other", rank=500)
        dub = models.Track(title="Dubstep Mix", artist="Skrillex", status="descargada",
                           source="test_bass", file_path="E:/b.mp3", genre="dubstep", rank=900)
        dnb = models.Track(title="Drum and Bass Session", artist="Sub Focus", status="descargada",
                           source="test_bass", file_path="E:/c.mp3", genre="dnb", rank=100)
        pop = models.Track(title="Levitating", artist="Dua Lipa", status="descargada",
                           source="test_bass", file_path="E:/d.mp3", genre="pop", rank=9999)
        # El portugués sigue fuera, también de esta lista.
        pt = models.Track(title="Bass Boosted Funk", artist="MC João", status="descargada",
                          source="test_bass", file_path="E:/e.mp3", genre="carbass",
                          language="pt", rank=9998)
        for t in (car, dub, dnb, pop, pt):
            db.add(t)
        db.commit()

        rebuild_remixes(db)

        pl = db.query(models.Playlist).filter_by(type="system", name="Bass y car music").first()
        assert pl, "no se creó la lista «Bass y car music»"
        ids = [f.track_id for f in db.query(models.PlaylistTrack)
               .filter_by(playlist_id=pl.id).order_by(models.PlaylistTrack.position).all()]
        assert dub.id in ids and dnb.id in ids and car.id in ids, ids
        assert pop.id not in ids and pt.id not in ids, ids
        # Ordenada por popularidad: el dubstep (rank 900) va antes que el car bass (500).
        assert ids.index(dub.id) < ids.index(car.id)

        # Y «Club y festival» incluye también estos géneros (es la música de pista del catálogo).
        club = db.query(models.Playlist).filter_by(type="system", name="Club y festival").first()
        club_ids = [f.track_id for f in db.query(models.PlaylistTrack).filter_by(playlist_id=club.id)]
        assert dub.id in club_ids and dnb.id in club_ids
    finally:
        db.query(models.PlaylistTrack).filter(
            models.PlaylistTrack.track_id.in_(
                [t.id for t in db.query(models.Track).filter_by(source="test_bass")])).delete()
        db.query(models.Playlist).filter_by(type="system", name="Bass y car music").delete()
        db.query(models.Track).filter_by(source="test_bass").delete()
        db.commit()
        db.close()
