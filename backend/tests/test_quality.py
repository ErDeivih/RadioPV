import radiov.quality as Q


def test_quality_rechaza_basura():
    ok, motivo = Q.revisar({"title": 'meta charset="utf-8"/', "artist": "x", "duration": 56})
    assert not ok and "HTML" in motivo


def test_quality_rechaza_artista_generico():
    ok, _ = Q.revisar({"title": "Ruido blanco para dormir", "artist": "Deezer", "duration": 36000})
    assert not ok


def test_quality_rechaza_duracion_fuera_rango():
    ok, motivo = Q.revisar({"title": "Larga", "artist": "Artista", "duration": 13000})
    assert not ok and "duración" in motivo


def test_quality_acepta_tema_normal():
    ok, motivo = Q.revisar({"title": "Sensualidad", "artist": "Bad Bunny", "duration": 210})
    assert ok and motivo == ""
