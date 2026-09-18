"""El recolector tiene que poder fallar y volver, y no morirse por escribir en su diario.

Contexto (18/09/2026): el hilo de trabajo del recolector MURIÓ y el contenedor siguió «arriba».
Por dentro no descargaba nada, por fuera parecía perfectamente sano, y así estuvo días: las altas
del catálogo pasaron de 590 un día a 14, y luego a cero. La causa fue un `db.log_event(...)`
dentro del propio manejador de errores: al escribir el evento, la base estaba cogida por el
análisis de audio y saltó «database is locked»; esa excepción se escapó del `except` y acabó con
el hilo. Un fallo al escribir una línea del registro no puede costar el recolector entero.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


# --- 1 · registrar un evento nunca puede lanzar --------------------------------------------------

def test_log_event_no_revienta_si_la_base_falla(monkeypatch, capsys):
    from radiov import db

    def sin_base():
        raise OSError("database is locked")

    monkeypatch.setattr(db, "get_conn", sin_base)
    db.log_event("esto tiene que poder registrarse sin tumbar nada", "error")

    salida = capsys.readouterr().out
    assert "database is locked" in salida, "el fallo debe quedar al menos en la salida"


def test_log_event_no_revienta_si_el_insert_falla(monkeypatch, capsys):
    from radiov import db

    class ConexionQueFalla:
        def execute(self, *a, **k):
            raise OSError("database is locked")

        def commit(self):
            raise OSError("database is locked")

        def close(self):
            pass

    monkeypatch.setattr(db, "get_conn", lambda: ConexionQueFalla())
    db.log_event("la escritura falla", "error")           # no debe lanzar
    assert "la escritura falla" in capsys.readouterr().out


def test_log_event_sigue_registrando_cuando_la_base_va_bien():
    """Que no lance no puede significar que no escriba: el registro se usa para diagnosticar."""
    import sqlite3
    from radiov import db

    antes = db.get_conn()
    try:
        n_antes = antes.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]
    finally:
        antes.close()

    db.log_event("prueba de que el registro sigue funcionando", "info")

    despues = db.get_conn()
    try:
        fila = despues.execute("SELECT message FROM events ORDER BY id DESC LIMIT 1").fetchone()
        n_despues = despues.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]
    finally:
        despues.close()
    assert n_despues == n_antes + 1
    assert "prueba de que el registro sigue funcionando" == fila["message"]


# --- 2 · saber si el hilo de trabajo sigue vivo --------------------------------------------------

class _HiloFalso:
    def __init__(self, vivo: bool):
        self.vivo = vivo

    def is_alive(self) -> bool:
        return self.vivo


def test_el_gestor_sabe_si_su_hilo_esta_vivo():
    """Sin esto, el supervisor del recolector no puede notar que su trabajador ha muerto."""
    from radiov.agent import AgentManager

    # Sin arrancar nada (nada de descargar en una prueba): se monta el objeto a mano.
    m = AgentManager.__new__(AgentManager)
    m._thread = None
    assert m.sigue_vivo() is False          # nunca arrancado
    m._thread = _HiloFalso(True)
    assert m.sigue_vivo() is True
    m._thread = _HiloFalso(False)
    assert m.sigue_vivo() is False          # arrancado pero muerto: el caso que dolió


# --- 3 · cuándo hay que reiniciar el contenedor --------------------------------------------------

def test_solo_se_reinicia_si_toca_descargar_y_el_hilo_esta_muerto():
    import importlib.util

    ruta = RAIZ / "run_collector.py"
    spec = importlib.util.spec_from_file_location("run_collector_prueba", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)          # sólo define cosas: `main()` no se ejecuta

    assert modulo.debe_reiniciarse(True, False) is True     # toca descargar y no hay quien lo haga
    assert modulo.debe_reiniciarse(True, True) is False     # todo en orden
    assert modulo.debe_reiniciarse(False, False) is False   # apagado a propósito: no se reinicia
    assert modulo.debe_reiniciarse(False, True) is False
