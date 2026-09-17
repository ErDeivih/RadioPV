"""El estado 'perdida' no puede deshacerlo la sincronización del catálogo.

Contexto del fallo (17/09/2026):

* `verificar_ficheros` (worker) marca `status='perdida'` las canciones cuyo fichero ya no está en
  el servidor. Eso es lo que las saca de la aplicación y las pone en la cola de re-descarga.
  Corre los **domingos a las 3:00**.
* `sync_catalogo` corre **cada 30 minutos** y copiaba el `status` desde `radiov.db`, que sigue
  diciendo 'descargada'. Así que la revisión semanal perdía siempre: la app seguía ofreciendo
  canciones que no se pueden reproducir (y el reproductor las intentaba y las saltaba).

La regla que se prueba aquí: si el fichero sigue sin estar, gana 'perdida'; la marca sólo se
levanta cuando el fichero ha vuelto de verdad.
"""
from pathlib import Path

import migrate_sqlite as M


def test_perdida_sobrevive_a_la_sincronizacion_si_el_fichero_sigue_faltando(tmp_path, monkeypatch):
    import app.paths as P

    monkeypatch.setattr(P, "resolve_music", lambda rel: tmp_path / rel)

    # El fichero NO existe → la marca se mantiene aunque el origen diga 'descargada'.
    assert M._estado_destino("perdida", "descargada", "no/existe.mp3") == "perdida"


def test_perdida_se_levanta_cuando_el_fichero_ha_vuelto(tmp_path, monkeypatch):
    import app.paths as P

    (tmp_path / "cancion.mp3").write_bytes(b"x")
    monkeypatch.setattr(P, "resolve_music", lambda rel: tmp_path / rel)

    # El fichero ya está (la copia de la música terminó) → vuelve a publicarse.
    assert M._estado_destino("perdida", "descargada", "cancion.mp3") == "descargada"


def test_sin_fichero_apuntado_no_se_publica(monkeypatch):
    # Sin `file_path` no hay nada que reproducir: se queda en 'perdida'.
    assert M._estado_destino("perdida", "descargada", None) == "perdida"
    assert M._estado_destino("perdida", "descargada", "") == "perdida"


def test_los_demas_estados_se_copian_tal_cual():
    # La regla sólo protege 'perdida': el resto de transiciones las manda el origen.
    assert M._estado_destino("descargada", "cuarentena", "x.mp3") == "cuarentena"
    assert M._estado_destino("cuarentena", "descargada", "x.mp3") == "descargada"
    assert M._estado_destino(None, "descargada", "x.mp3") == "descargada"
    assert M._estado_destino(None, "incompleta", None) == "incompleta"
    assert M._estado_destino("retirada", "retirada", "x.mp3") == "retirada"


def test_si_no_se_puede_comprobar_el_fichero_se_mantiene_perdida(monkeypatch):
    import app.paths as P

    def revienta(_rel):
        raise OSError("disco no disponible")

    monkeypatch.setattr(P, "resolve_music", revienta)
    # Es más honesto no ofrecer algo que puede no sonar que ofrecerlo y fallar.
    assert M._estado_destino("perdida", "descargada", "x.mp3") == "perdida"


def test_ruta_absoluta_inexistente(tmp_path, monkeypatch):
    import app.paths as P

    monkeypatch.setattr(P, "resolve_music", lambda rel: Path(rel))
    assert M._estado_destino("perdida", "descargada", str(tmp_path / "nada.mp3")) == "perdida"
