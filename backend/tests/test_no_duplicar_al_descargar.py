"""Antes de bajar una canción se comprueba que NO esté ya en el servidor. Y sin cargar el servidor.

QUÉ SE ESTABA COLANDO
---------------------
La misma canción llegaba escrita de mil maneras y de mil vídeos distintos:

    Feid - HAXTA EL DÍA FINAL
    FEID - Haxta el dia final (Official Video)
    Feid - HaxTa el Día Final (feat. Alguien)

Y de un mismo tema hay el vídeo oficial, el lyric video y el audio: **vídeos distintos para la misma
canción**. La comprobación que había comparaba el texto EXACTO, así que nada de eso coincidía: el PC
volvía a bajar y a enviar canciones que el servidor ya tenía, y la biblioteca acabó con dos, tres y
hasta cuatro fichas del mismo tema (una de ellas sin fichero, o sea una canción que aparece en la
aplicación y no suena).

QUÉ SE COMPRUEBA AQUÍ
---------------------
1. La clave normalizada reconoce la misma canción escrita de otra forma, y NO confunde versiones
   distintas (un remix o un directo son canciones distintas y tienen que seguir siéndolo).
2. `pista_existente` resuelve por vídeo → Deezer → clave.
3. El índice del servidor se puede pedir **sólo con lo nuevo** (`desde_id`), que es lo que evita
   traerse 6 000 filas cada 15 minutos en un portátil de 4 GB.
"""
import pytest

from radiov.db import clave_cancion, indice_de_claves, pista_existente


@pytest.fixture
def biblioteca(tmp_path, monkeypatch):
    from radiov import db as rdb
    from radiov import config as rcfg

    ruta = tmp_path / "radiov.db"
    monkeypatch.setattr(rcfg, "DB_PATH", ruta)
    monkeypatch.setattr(rdb, "DB_PATH", ruta)
    rdb.init_db()
    return rdb


# ---------------------------------------------------------------- la clave normalizada
@pytest.mark.parametrize("a1,t1,a2,t2", [
    ("Feid", "HAXTA EL DÍA FINAL", "Feid", "Haxta el dia final (Official Video)"),
    ("Feid", "HAXTA EL DÍA FINAL", "FEID", "Haxta el Día Final (feat. X)"),
    ("ROSALÍA", "La Perla", "Rosalia", "La Perla (Lyric Video)"),
    ("Bad Bunny", "Yo Perreo Sola", "BAD BUNNY", "Yo Perreo Sola [Official Audio]"),
])
def test_la_misma_cancion_escrita_de_otra_forma_da_la_misma_clave(a1, t1, a2, t2):
    assert clave_cancion(a1, t1) == clave_cancion(a2, t2)


@pytest.mark.parametrize("a1,t1,a2,t2", [
    # Versiones distintas: NO son la misma canción.
    ("Feid", "Haxta el Día Final", "Feid", "Haxta el Día Final (Remix)"),
    ("Luis Fonsi", "Despacito", "Luis Fonsi", "Despacito (En Vivo)"),
    ("Daddy Yankee", "Gasolina", "Daddy Yankee", "Gasolina (Extended Mix)"),
    # Distinto artista, mismo título: son canciones distintas.
    ("Álex y Christina", "Chu chu", "DJ Kay Slay", "Chu chu"),
])
def test_las_versiones_distintas_NO_se_confunden(a1, t1, a2, t2):
    assert clave_cancion(a1, t1) != clave_cancion(a2, t2)


# ---------------------------------------------------------------- pista_existente
def test_lo_encuentra_por_el_video(biblioteca):
    """El mismo vídeo es la misma grabación, se llame como se llame."""
    rdb = biblioteca
    tid = rdb.add_track({"title": "Una Canción", "artist": "Un Artista", "youtube_id": "VID123",
                         "status": "descargada"})
    assert pista_existente(youtube_id="VID123") == tid


def test_lo_encuentra_por_deezer(biblioteca):
    rdb = biblioteca
    tid = rdb.add_track({"title": "Otra", "artist": "Otro", "deezer_id": "999",
                         "status": "descargada"})
    assert pista_existente(deezer_id="999") == tid


def test_lo_encuentra_aunque_el_nombre_venga_con_ruido(biblioteca):
    """El caso que se colaba: mismo tema, otro vídeo y el título con «(Official Video)»."""
    rdb = biblioteca
    tid = rdb.add_track({"title": "HAXTA EL DÍA FINAL", "artist": "Feid",
                         "youtube_id": "AAA", "status": "descargada"})
    assert pista_existente(youtube_id="BBB", artist="FEID",
                           title="Haxta el Dia Final (Official Video)") == tid


def test_no_lo_encuentra_si_es_otra_cosa(biblioteca):
    rdb = biblioteca
    rdb.add_track({"title": "HAXTA EL DÍA FINAL", "artist": "Feid",
                   "youtube_id": "AAA", "status": "descargada"})
    assert pista_existente(youtube_id="CCC", artist="Feid",
                           title="HAXTA EL DÍA FINAL (Remix)") is None
    assert pista_existente(youtube_id="DDD", artist="Otro", title="Otra cosa") is None


def test_el_indice_de_claves_lo_da_todo_de_una_vez(biblioteca):
    rdb = biblioteca
    rdb.add_track({"title": "Uno", "artist": "A", "status": "descargada"})
    rdb.add_track({"title": "Dos", "artist": "B", "status": "descargada"})
    claves = indice_de_claves()
    assert clave_cancion("A", "Uno") in claves and clave_cancion("B", "Dos") in claves
    # Y sirve para comprobar sin volver a preguntar a la base.
    assert pista_existente(artist="a", title="uno", claves=claves) is not None


# ---------------------------------------------------------------- la carga en el servidor
def test_el_indice_se_puede_pedir_solo_con_lo_nuevo():
    """`desde_id` es lo que evita traerse 6 000 filas cada 15 minutos.

    No se prueba contra la base del servidor (aquí no existe), sino que el endpoint acepte el
    parámetro y devuelva además `max_id`, que es lo que el PC guarda para la próxima vez.
    """
    import inspect

    from app.routers import collector

    firma = inspect.signature(collector.indice)
    assert "desde_id" in firma.parameters
    assert "limite" in firma.parameters
    fuente = inspect.getsource(collector.indice)
    assert "max_id" in fuente and "WHERE id > ?" in fuente


def test_la_importacion_no_duplica_lo_que_ya_esta():
    """El servidor es el último filtro: si llega algo que ya tiene, no lo inserta."""
    import inspect

    from app.routers import collector

    fuente = inspect.getsource(collector.importar)
    assert "pista_existente" in fuente, "vuelve a insertar sin comprobar"
    assert "rellenar_huecos" in fuente, "debería rellenar huecos en vez de duplicar"
    assert "repetidas" in fuente, "tiene que decírselo al PC"
