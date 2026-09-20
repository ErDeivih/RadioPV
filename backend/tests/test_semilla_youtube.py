"""Una semilla de YouTube tiene que traer TODAS las canciones de su cupo, no sólo la primera.

EL FALLO QUE FIJA ESTA PRUEBA (encontrado el 20/09/2026)
--------------------------------------------------------
`process_youtube_seed` guardaba la canción recién bajada en el índice de claves con
`claves.add(...)`, pero `indice_de_claves()` devuelve un **diccionario** `{clave: id}` (antes era un
conjunto). Con el `.add()` esa línea lanzaba `AttributeError` y **mataba la búsqueda entera en cuanto
bajaba la primera canción**: cada semilla de YouTube podía traer 1 canción por vuelta en vez de las 6
de su cupo. El recolector lo apuntaba como «Fallo en semilla» sin decir por qué, así que llevaba
días bajando de menos sin que se notara — justo el contenido que el usuario más escucha (mashups,
sesiones de DJ, remixes y ahora el tech house).

La prueba pone 3 candidatos y comprueba que se bajan los 3 y que la cuarta búsqueda no vuelve a bajar
lo mismo (que es para lo que sirve el índice de claves).
"""
import pytest


@pytest.fixture
def semilla(monkeypatch):
    """Una semilla de YouTube con 3 candidatos distintos y una descarga de mentira que funciona."""
    from radiov import youtube

    candidatos = [
        {"id": "vid-1", "title": "Pomata - El Farsante (Tech House Remix)", "duration": 180},
        {"id": "vid-2", "title": "Mau P - Drugs From Amsterdam (Tech House Remix)", "duration": 200},
        {"id": "vid-3", "title": "Andruss - Frikitona (Guaracha Remix)", "duration": 190},
    ]
    monkeypatch.setattr(youtube, "search_videos", lambda q, n=15: list(candidatos))
    monkeypatch.setattr(youtube, "download_video",
                        lambda vid, artist="", title="": {"youtube_id": vid, "path": f"E:/{vid}.mp3",
                                                          "youtube_duration": 180,
                                                          "title": title, "artist": artist})
    from radiov import pipeline
    return pipeline, candidatos


def _por_video(vid: str) -> dict | None:
    """La ficha de un vídeo concreto (por su id de YouTube)."""
    from radiov import db as rdb
    con = rdb.get_conn()
    try:
        fila = con.execute("SELECT * FROM tracks WHERE youtube_id=?", (vid,)).fetchone()
        return dict(fila) if fila else None
    finally:
        con.close()


def _limpiar():
    from radiov import db as rdb
    for vid in ("vid-1", "vid-2", "vid-3"):
        p = _por_video(vid)
        if p:
            rdb.delete_track(p["id"])


def test_una_semilla_trae_todas_las_canciones_del_cupo(semilla):
    pipeline, candidatos = semilla
    _limpiar()
    try:
        añadidas = pipeline.process_youtube_seed(
            {"mode": "youtube", "query": "tech house remix", "genre": "techhouse", "language": "es"},
            max_downloads=3)
        assert añadidas == 3, f"sólo se bajaron {añadidas} de {len(candidatos)} candidatos"
    finally:
        _limpiar()


def test_lo_ya_bajado_no_se_vuelve_a_bajar(semilla):
    """El índice de claves se actualiza al bajar: la segunda pasada no repite trabajo."""
    pipeline, _ = semilla
    _limpiar()
    try:
        primera = pipeline.process_youtube_seed(
            {"mode": "youtube", "query": "tech house remix", "genre": "techhouse", "language": "es"},
            max_downloads=3)
        assert primera == 3
        segunda = pipeline.process_youtube_seed(
            {"mode": "youtube", "query": "tech house remix", "genre": "techhouse", "language": "es"},
            max_downloads=3)
        assert segunda == 0, "se volvieron a bajar canciones que ya estaban"
    finally:
        _limpiar()


def test_la_cancion_bajada_lleva_el_genero_de_la_semilla(semilla):
    """Y el género del tech house es el nuevo, no «other»: es lo que hace que salga en su lista."""
    pipeline, _ = semilla
    _limpiar()
    try:
        pipeline.process_youtube_seed(
            {"mode": "youtube", "query": "tech house remix", "genre": "techhouse", "language": "es"},
            max_downloads=1)
        # Los candidatos se barajan a propósito en `process_youtube_seed` (no siempre los mismos
        # primeros resultados), así que se mira cuál de los tres se bajó, no uno en concreto.
        pista = next((p for p in (_por_video(v) for v in ("vid-1", "vid-2", "vid-3")) if p), None)
        assert pista, "no se guardó ninguna canción"
        assert pista["genre"] == "techhouse", pista["genre"]
    finally:
        _limpiar()
