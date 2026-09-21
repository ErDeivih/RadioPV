"""Publicar lo que viene de YouTube no puede exigir datos que YouTube no tiene.

FALLO REAL (19/09/2026)
-----------------------
En el PC quedaban canciones bajadas de YouTube en estado `incompleta` **para siempre**:

    aviso: 18 descargadas aún sin completar; se mandarán cuando lo estén

Se les pedía año, género, idioma, BPM, energía, ganancia, duración y carátula. Deezer no tiene ficha
de un mashup casero ni de una sesión de DJ, así que el **año** no había de dónde sacarlo: bajaban, se
analizaban, se les ponía hasta la carátula… y no llegaban NUNCA a la aplicación. Entre ellas, la
sesión de 36 minutos que el usuario había pedido a mano desde la página de pedir canciones.

Ahora, cuando la canción viene de un vídeo de YouTube, el año no bloquea: se publica sin él. La
decisión es deliberada: **mejor una canción que suena sin fecha que una fecha perfecta que no suena**.
"""
import pytest


@pytest.fixture
def base_temporal(tmp_path, monkeypatch):
    from radiov import db as rdb
    from radiov import config as rcfg

    ruta = tmp_path / "radiov.db"
    monkeypatch.setattr(rcfg, "DB_PATH", ruta)
    monkeypatch.setattr(rdb, "DB_PATH", ruta)
    rdb.init_db()
    return rdb


def _pista(rdb, **extra):
    base = {"title": "Mashup De Prueba", "artist": "DJ Prueba", "status": "incompleta",
            "source": "agente", "file_path": "catalogada/x.mp3", "genre": "pop",
            "language": "es", "bpm": 120.0, "energy": 0.5, "gain_db": -7.0, "duration": 200.0,
            "cover_url": "https://i.ytimg.com/vi/X/hqdefault.jpg"}
    base.update(extra)
    return rdb.add_track(base)


def test_lo_bajado_de_youtube_se_publica_aunque_no_tenga_ano(base_temporal):
    from radiov import catalog as C

    rdb = base_temporal
    tid = _pista(rdb, youtube_id="VIDEO123")          # sin `year`, como un mashup real
    assert C.republicar_completas() >= 1

    con = rdb.get_conn()
    try:
        estado = con.execute("SELECT status FROM tracks WHERE id=?", (tid,)).fetchone()[0]
    finally:
        con.close()
    assert estado == "descargada", "una canción de YouTube sin año se queda sin publicar"


def test_una_cancion_de_tienda_sin_ano_SIGUE_sin_publicarse(base_temporal):
    """El año sólo deja de exigirse cuando NO HAY de dónde sacarlo.

    De una canción de tienda (con `deezer_id`) el año existe y se puede traer: se sigue esperando. Lo
    que no puede es exigírsele a un fichero recuperado del disco, que no tiene ni vídeo ni ficha — ver
    `test_lo_recuperado_del_disco_tambien_se_publica`.
    """
    from radiov import catalog as C

    rdb = base_temporal
    tid = _pista(rdb, youtube_id=None, deezer_id="12345")     # de tienda, pero sin año
    C.republicar_completas()

    con = rdb.get_conn()
    try:
        estado = con.execute("SELECT status FROM tracks WHERE id=?", (tid,)).fetchone()[0]
    finally:
        con.close()
    assert estado == "incompleta"


def test_lo_recuperado_del_disco_tambien_se_publica(base_temporal):
    """167 canciones recuperadas del disco se quedaron 'incompleta' PARA SIEMPRE (21/09/2026).

    No tienen `youtube_id` (el fichero ya estaba en el disco, nadie sabe de qué vídeo salió) ni ficha
    de tienda, así que ni año ni carátula se podían conseguir. Con la regla vieja —la excepción del año
    sólo para vídeos— se quedaban en el disco, medidas y sin llegar nunca a la aplicación.
    """
    from radiov import catalog as C

    rdb = base_temporal
    tid = _pista(rdb, source="recuperada", cover_url=None, youtube_id=None)
    assert C.republicar_completas() >= 1

    con = rdb.get_conn()
    try:
        estado = con.execute("SELECT status FROM tracks WHERE id=?", (tid,)).fetchone()[0]
    finally:
        con.close()
    assert estado == "descargada", "una canción recuperada y ya medida se queda sin publicar"


def test_sigue_haciendo_falta_lo_demas(base_temporal):
    """Quitar el año no puede abrir la puerta a publicar tracks a medias."""
    from radiov import catalog as C

    rdb = base_temporal
    tid = _pista(rdb, youtube_id="VIDEO999", gain_db=None)   # falta la ganancia
    C.republicar_completas()

    con = rdb.get_conn()
    try:
        estado = con.execute("SELECT status FROM tracks WHERE id=?", (tid,)).fetchone()[0]
    finally:
        con.close()
    assert estado == "incompleta", "sin ganancia no se publica: la canción sonaría a otro volumen"
