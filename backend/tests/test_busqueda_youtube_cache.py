"""La búsqueda en YouTube se guarda un rato: este servidor es un portátil de 4 GB.

POR QUÉ
-------
Buscar en YouTube lanza `yt-dlp`, que es un **proceso de Python entero** (y encima tarda ~2 s). La
página de pedir canciones busca **mientras se escribe**: sin caché, cada consulta —y cada vuelta a
la pantalla, y cada persona que escriba lo mismo— arrancaba un proceso nuevo en la máquina que
también sirve la aplicación. YouTube además limita si se le pregunta demasiado seguido.

Estas pruebas fijan que:
  · la segunda búsqueda igual NO llama a YouTube (ni abre proceso),
  · una búsqueda distinta sí,
  · lo guardado no se puede estropear desde fuera (se devuelve una copia),
  · y se puede pedir que pregunte de nuevo (`usar_cache=False`), que es lo que necesita el
    recolector cuando quiere variedad y baraja los resultados.
"""
import pytest

from radiov import youtube


@pytest.fixture
def sin_cache(monkeypatch):
    """Caché vacía y `_search_candidates` contado, sin tocar la red."""
    llamadas = []

    def falso(query, n=8):
        llamadas.append((query, n))
        return [{"id": f"V{len(llamadas)}", "title": f"{query} {n}", "duration": 120}]

    monkeypatch.setattr(youtube, "_search_candidates", falso)
    monkeypatch.setattr(youtube, "_CACHE", {})
    return llamadas


def test_la_segunda_busqueda_igual_no_vuelve_a_preguntar(sin_cache):
    a = youtube.search_videos("mashup reggaeton", 12)
    b = youtube.search_videos("mashup reggaeton", 12)
    assert len(sin_cache) == 1, "la segunda búsqueda ha vuelto a lanzar yt-dlp"
    assert a == b


def test_la_misma_busqueda_con_otro_numero_si_pregunta(sin_cache):
    youtube.search_videos("mashup", 10)
    youtube.search_videos("mashup", 20)
    assert len(sin_cache) == 2, "el número de resultados es parte de la consulta"


def test_no_distingue_mayusculas_ni_espacios(sin_cache):
    youtube.search_videos("Sesion de Reggaeton", 12)
    youtube.search_videos("  sesion de reggaeton  ", 12)
    assert len(sin_cache) == 1


def test_lo_guardado_no_se_puede_estropear_desde_fuera(sin_cache):
    """El recolector baraja los resultados: eso no puede cambiar lo que hay en la caché."""
    primera = youtube.search_videos("sesion dj", 12)
    primera.clear()
    primera.append({"id": "BASURA"})
    segunda = youtube.search_videos("sesion dj", 12)
    assert segunda and segunda[0]["id"] != "BASURA"


def test_se_puede_pedir_que_pregunte_de_nuevo(sin_cache):
    """Para el recolector: quiere resultados frescos para no bajar siempre lo mismo."""
    youtube.search_videos("mashup", 12)
    youtube.search_videos("mashup", 12, usar_cache=False)
    assert len(sin_cache) == 2


def test_si_la_busqueda_falla_no_se_guarda_nada(sin_cache, monkeypatch):
    """Un fallo no puede quedar cacheado: si no, la página se quedaría sin resultados 10 minutos."""
    monkeypatch.setattr(youtube, "_search_candidates", lambda q, n=8: [])
    youtube.search_videos("algo sin resultados", 12)
    assert youtube._CACHE == {}


def test_la_cache_no_crece_sin_limite(sin_cache, monkeypatch):
    """En 4 GB de RAM no se puede guardar todo lo que se busque."""
    monkeypatch.setattr(youtube, "_MAX_BUSQUEDAS", 5)
    for i in range(12):
        youtube.search_videos(f"consulta {i}", 12)
    assert len(youtube._CACHE) <= 6, "la caché tiene que ir soltando lo viejo"
