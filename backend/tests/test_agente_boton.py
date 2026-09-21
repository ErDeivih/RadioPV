"""El agente del botón del PC: lo que se puede probar sin apagar nada.

EL FALLO QUE FIJA ESTA PRUEBA (21/09/2026, recién montado)
-----------------------------------------------------------
El agente llamaba a `http://servidor:8090/api/boton/...` (la API del recolector) cuando el botón
vive en **otro servicio y otro puerto** (`8099`). Y como cualquier fallo devolvía `{}` —igual que
«no hay órdenes»—, el botón del móvil no hacía nada y **nadie sabía por qué**: la única pista era
un latido que nunca llegaba.

Estas pruebas comprueban las dos mitades de eso:
  · que las órdenes se traducen al comando correcto y que el MODO PRUEBA no ejecuta nada;
  · que un fallo de red o un 403 se cuentan como error, en vez de parecer «todo bien».
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "pc") not in sys.path:
    sys.path.insert(0, str(RAIZ / "pc"))

import agente_boton  # noqa: E402


def test_el_modo_prueba_no_ejecuta_nada():
    """El modo prueba tiene que DEVOLVER el comando, no lanzarlo: es la red de seguridad."""
    for orden in ("apagar", "reiniciar", "suspender", "cancelar"):
        texto = agente_boton.ejecutar(orden, probar=True)
        assert texto.startswith("(PRUEBA)"), texto
        assert "shutdown" in texto or "SetSuspendState" in texto, texto


def test_cada_orden_usa_lo_que_toca():
    assert "shutdown /s" in agente_boton.ejecutar("apagar", probar=True)
    assert "shutdown /r" in agente_boton.ejecutar("reiniciar", probar=True)
    assert "shutdown /a" in agente_boton.ejecutar("cancelar", probar=True)
    # Suspender NO puede ser `rundll32 powrprof.dll,SetSuspendState`: con la hibernación activada
    # eso HIBERNA, y desde hibernación el Wake-on-LAN es menos fiable.
    suspender = agente_boton.ejecutar("suspender", probar=True)
    assert "SetSuspendState('Suspend'" in suspender, suspender
    assert "powrprof" not in suspender, suspender


def test_una_orden_desconocida_no_hace_nada():
    assert "desconocida" in agente_boton.ejecutar("formatear", probar=True)


def test_las_ordenes_permitidas_son_las_cuatro():
    assert set(agente_boton.ORDENES) == {"apagar", "reiniciar", "suspender", "cancelar"}


def test_el_apagado_da_margen_para_cancelarlo():
    """20 segundos: si te equivocas de botón en el móvil, hay tiempo de deshacerlo."""
    assert agente_boton.SEGUNDOS_DE_AVISO >= 10


def test_un_fallo_no_parece_una_respuesta_vacia(monkeypatch):
    """Un 403 o una dirección mal puesta tienen que salir como ERROR, no como «no hay órdenes»."""
    import urllib.error

    def revienta(*_a, **_k):
        raise urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)

    monkeypatch.setattr(agente_boton.urllib.request, "urlopen", revienta)
    datos, error = agente_boton._pedir("http://x/boton/orden", "token")
    assert datos == {} and error, "un 403 no puede parecer «no hay órdenes»"
    assert "403" in error, error


def test_si_el_servidor_no_esta_se_dice_que_no_se_pudo(monkeypatch):
    import urllib.error

    def revienta(*_a, **_k):
        raise urllib.error.URLError("conexión rechazada")

    monkeypatch.setattr(agente_boton.urllib.request, "urlopen", revienta)
    _datos, error = agente_boton._pedir("http://x/boton/orden", "token")
    assert "no se pudo contactar" in error, error
