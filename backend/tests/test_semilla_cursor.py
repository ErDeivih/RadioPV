"""El recolector del PC no puede empezar SIEMPRE por las mismas semillas.

EL FALLO QUE FIJA ESTA PRUEBA (encontrado el 20/09/2026)
--------------------------------------------------------
El agente recorre las semillas con un contador en memoria (`seed_cursor`) que empieza en 0 en cada
proceso, y **cada vuelta del recolector es un proceso nuevo**. La vuelta termina al llegar a su tope
(6 canciones o 12 minutos), así que siempre se quedaba en las primeras semillas de la lista: de las
92 semillas de YouTube, las 37 de tech house están en los puestos 56 a 92, o sea que era imposible
que se ejecutara ni una. El usuario veía «las semillas nuevas no traen nada» y el registro no decía
por qué.

La solución: guardar por qué semilla se quedó la vuelta anterior y empezar por la siguiente.
"""
import json
import time as _time

import pytest


@pytest.fixture
def recolector(tmp_path):
    """El módulo del recolector con su carpeta de datos en un directorio temporal."""
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    if str(raiz / "pc") not in sys.path:
        sys.path.insert(0, str(raiz / "pc"))
    import recolector_pc

    return recolector_pc, {"datos_locales": str(tmp_path)}


def test_sin_fichero_empieza_por_la_primera(recolector):
    rcp, cfg = recolector
    assert rcp._leer_estado_semilla(cfg) == 0


def test_el_por_donde_ibamos_se_guarda(recolector):
    rcp, cfg = recolector
    rcp._guardar_estado_semilla(cfg, 57, 92)
    assert rcp._leer_estado_semilla(cfg) == 57
    datos = json.loads((rcp._ruta_estado_semilla(cfg)).read_text(encoding="utf-8"))
    assert datos["total"] == 92 and "cuando" in datos


def test_una_vuelta_continua_donde_se_quedo_la_anterior(recolector, monkeypatch):
    """La segunda vuelta NO vuelve a empezar por la semilla 0."""
    rcp, cfg = recolector
    rcp._guardar_estado_semilla(cfg, 55, 92)

    class GestorDeMentira:
        """Hace lo mínimo que `recolectar` usa: el contador, las semillas y el estado."""

        def __init__(self):
            self.seed_cursor = 0
            self.encendido = False

        def set_agent(self, valor):
            self.encendido = valor

        def _semillas(self):
            return [{"query": f"s{i}"} for i in range(92)]

        def snapshot(self):
            return {"seed_cursor": self.seed_cursor}

    gestor = GestorDeMentira()
    monkeypatch.setattr("radiov.agent.get_manager", lambda: gestor)
    # Una sola pasada del bucle: sin esto la prueba espera 10 s de verdad.
    monkeypatch.setattr(rcp, "time", type("T", (), {"sleep": staticmethod(lambda s: None),
                                                    "time": staticmethod(_time.time)}))

    añadidas = rcp.recolectar(cfg, minutos=0, maximo=0)

    assert añadidas == 0
    assert gestor.seed_cursor == 55, "la vuelta no empezó por donde se quedó la anterior"
    # Y al terminar deja apuntado por dónde iba, para la siguiente.
    assert rcp._leer_estado_semilla(cfg) == 55
