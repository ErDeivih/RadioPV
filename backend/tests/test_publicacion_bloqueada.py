"""Lo que NO se puede saber no puede bloquear una canción para siempre.

DOS BLOQUEOS REALES (encontrados el 21/09/2026, con el catálogo delante)
-----------------------------------------------------------------------
1. **Bloqueo mutuo con el BPM.** El análisis de BPM pedía `status='descargada'`, pero una pista no
   llega a 'descargada' hasta que tiene BPM: sólo se analizaban las ya publicadas y publicarse exigía
   el BPM. Una pista 'incompleta' sin BPM no se analizaba nunca → no se publicaba nunca. Se veía en el
   recolector como «aviso: 179 descargadas aún sin completar» vuelta tras vuelta.

2. **El año y la carátula bloqueaban a lo que no tiene de dónde sacarlos.** La excepción del año
   estaba puesta sólo para las canciones con `youtube_id`, y la de la carátula no existía. Las 167
   canciones recuperadas del disco (sin vídeo y sin ficha de tienda) se quedaban 'incompleta' **para
   siempre**: en el disco, medidas, y sin llegar nunca a la aplicación.

Aquí se fijan las dos, y sobre todo la SEGUNDA MITAD de la regla: que siga exigiendo todo lo que sí
se puede sacar del propio audio (género, idioma, duración, energía, ganancia y BPM).
"""
import pytest

from radiov.catalog import CAMPOS_OBLIGATORIOS, campos_que_faltan


def _completa(**extra) -> dict:
    base = {"genre": "pop", "language": "es", "bpm": 120.0, "energy": 0.5, "gain_db": -6.0,
            "duration": 200.0}
    base.update(extra)
    return base


def test_falta_todo_lo_que_se_puede_medir():
    """Sin nada, se exige todo menos lo que no se puede saber (año y carátula de un fichero suelto)."""
    faltan = campos_que_faltan({"title": "Una mezcla", "artist": "Alguien"})
    assert "year" not in faltan and "cover_url" not in faltan
    for campo in ("genre", "language", "bpm", "energy", "gain_db", "duration"):
        assert campo in faltan, campo


def test_una_cancion_de_youtube_puede_publicarse_sin_ano_pero_con_caratula():
    """El vídeo trae su miniatura; el año sí se perdona (Deezer no tiene ficha de un mashup)."""
    faltan = campos_que_faltan({"youtube_id": "abc", "cover_url": "http://x/c.jpg"})
    assert "year" not in faltan
    assert "cover_url" not in faltan
    faltan_sin_caratula = campos_que_faltan({"youtube_id": "abc"})
    assert "cover_url" in faltan_sin_caratula, "de una canción de YouTube sí se espera carátula"


def test_una_cancion_de_tienda_si_tiene_que_traer_ano():
    """Si hay ficha de Deezer, el año es un dato que existe: no se publica sin él."""
    faltan = campos_que_faltan(_completa(deezer_id="123", cover_url="http://x/c.jpg"))
    assert faltan == ["year"], faltan
    assert not campos_que_faltan(_completa(deezer_id="123", cover_url="http://x/c.jpg", year=2020))


def test_una_recuperada_del_disco_se_publica_cuando_esta_medida():
    """El caso de las 167: sin vídeo ni tienda, con el audio medido, tiene que publicarse."""
    assert campos_que_faltan(_completa(source="recuperada")) == []
    # Y con la carátula puesta por Deezer tampoco cambia nada.
    assert campos_que_faltan(_completa(source="recuperada", cover_url="http://x/c.jpg")) == []


def test_la_lista_de_obligatorios_no_se_queda_corta():
    """Si alguien añade un campo obligatorio, esta prueba obliga a mirarlo (y a documentarlo)."""
    assert set(CAMPOS_OBLIGATORIOS) == {"year", "genre", "language", "bpm", "energy", "gain_db",
                                        "duration", "cover_url"}


def test_el_analisis_de_bpm_ya_no_se_queda_solo_con_las_publicadas(client, tmp_path, monkeypatch):
    """El bloqueo mutuo: una 'incompleta' sin BPM tiene que entrar en el lote de análisis."""
    from radiov import db as rdb
    from radiov import models as M
    from radiov import config as cfg

    ruta = tmp_path / "radiov.db"
    monkeypatch.setattr(cfg, "DB_PATH", ruta)
    monkeypatch.setattr(rdb, "DB_PATH", ruta)
    rdb.init_db()

    def alta(titulo, estado, **extra):
        rec = {"title": titulo, "artist": "Pruebas BPM", "status": estado,
               "file_path": f"catalogada/{titulo}.mp3", "source": "prueba"}
        rec.update(extra)
        return rdb.add_track(rec)

    incompleta = alta("Incompleta sin bpm", "incompleta")
    publicada = alta("Publicada sin bpm", M.STATUS_DOWNLOADED)
    cuarentena = alta("En cuarentena sin bpm", M.STATUS_QUARANTINE)
    sin_fichero = alta("Sin fichero", "incompleta", file_path="")

    ids = [p["id"] for p in rdb.get_tracks_needing_bpm(limit=50)]
    assert incompleta in ids, "una 'incompleta' sin BPM nunca se analizaría (bloqueo mutuo)"
    assert publicada in ids
    assert cuarentena not in ids, "no se gasta CPU en lo que está fuera de circulación"
    assert sin_fichero not in ids, "sin fichero no hay nada que analizar"


def test_republicar_saca_lo_que_ya_esta_medido(client, tmp_path, monkeypatch):
    """Y el republicador publica la recuperada medida, sin exigirle año ni carátula."""
    from radiov import db as rdb
    from radiov import models as M
    from radiov import config as cfg
    from radiov.catalog import republicar_completas

    ruta = tmp_path / "radiov.db"
    monkeypatch.setattr(cfg, "DB_PATH", ruta)
    monkeypatch.setattr(rdb, "DB_PATH", ruta)
    rdb.init_db()

    lista = rdb.add_track({"title": "Recuperada medida", "artist": "Alguien", "status": "incompleta",
                           "source": "recuperada", "file_path": "catalogada/x.mp3",
                           "genre": "other", "language": "es", "bpm": 120.0, "energy": 0.5,
                           "gain_db": -6.0, "duration": 200.0})
    pendiente = rdb.add_track({"title": "Recuperada sin medir", "artist": "Alguien",
                               "status": "incompleta", "source": "recuperada",
                               "file_path": "catalogada/y.mp3", "duration": 200.0})

    republicar_completas(limit=50)

    con = rdb.get_conn()
    try:
        estados = {r["id"]: r["status"] for r in con.execute(
            "SELECT id, status FROM tracks WHERE id IN (?,?)", (lista, pendiente))}
    finally:
        con.close()
    assert estados[lista] == M.STATUS_DOWNLOADED, "la que ya está medida tenía que publicarse"
    assert estados[pendiente] == "incompleta", "a la que le falta el análisis no se toca"
