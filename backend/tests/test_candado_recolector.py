"""El candado del recolector no puede dejar el PC tres horas sin descargar.

EL FALLO QUE FIJA ESTA PRUEBA (21/09/2026)
------------------------------------------
El candado caducaba a las 3 horas y no miraba si el proceso seguía existiendo. La vuelta de las 06:47
murió a mitad sin borrar su candado, y **todas las vueltas siguientes salieron sin hacer nada**
(«Ya hay otra vuelta en marcha») hasta pasadas las 09:47: tres horas sin descargar ni publicar, y en
el registro parecía que el recolector estaba trabajando.

Ahora el candado guarda el PID y se comprueba si ese proceso vive.
"""
import os
import sys
import time
from pathlib import Path


def _recolector():
    raiz = Path(__file__).resolve().parents[2]
    if str(raiz / "pc") not in sys.path:
        sys.path.insert(0, str(raiz / "pc"))
    import recolector_pc
    return recolector_pc


def _cfg(tmp_path):
    return {"datos_locales": str(tmp_path)}


def test_sin_candado_se_toma(tmp_path):
    rcp = _recolector()
    candado = rcp._bloqueo(_cfg(tmp_path))
    assert candado is not None
    assert candado.exists()
    assert candado.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_un_candado_de_un_proceso_vivo_para_la_vuelta(tmp_path):
    """Si de verdad hay otra vuelta, no se la pisa (esto ya funcionaba y no puede romperse)."""
    rcp = _recolector()
    cfg = _cfg(tmp_path)
    ruta = Path(cfg["datos_locales"]) / "recolector_pc.lock"
    ruta.write_text(str(os.getpid()), encoding="utf-8")      # este proceso SÍ existe
    assert rcp._bloqueo(cfg) is None


def test_un_candado_de_un_proceso_muerto_no_bloquea(tmp_path):
    """El caso de las 06:47: el proceso ya no está, así que la vuelta tiene que arrancar."""
    rcp = _recolector()
    cfg = _cfg(tmp_path)
    ruta = Path(cfg["datos_locales"]) / "recolector_pc.lock"
    ruta.write_text("999999", encoding="utf-8")              # un PID que no existe
    candado = rcp._bloqueo(cfg)
    assert candado is not None, "un candado de una vuelta muerta bloqueaba el recolector"
    assert candado.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_un_candado_viejo_caduca_aunque_el_pid_parezca_vivo(tmp_path):
    """Los PIDs se reciclan: pasado el plazo, se toma el relevo igual."""
    rcp = _recolector()
    cfg = _cfg(tmp_path)
    ruta = Path(cfg["datos_locales"]) / "recolector_pc.lock"
    ruta.write_text(str(os.getpid()), encoding="utf-8")
    viejo = time.time() - (rcp.CADUCIDAD_CANDADO + 60)
    os.utime(ruta, (viejo, viejo))
    assert rcp._bloqueo(cfg) is not None


def test_el_plazo_no_es_una_eternidad():
    """Tres horas eran demasiado: una vuelta normal dura 12-20 minutos."""
    rcp = _recolector()
    assert rcp.CADUCIDAD_CANDADO <= 60 * 60
