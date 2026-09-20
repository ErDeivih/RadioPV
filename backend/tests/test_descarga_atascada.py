"""Una descarga atascada no puede llevarse por delante la tarde entera.

FALLO REAL (20/09/2026)
-----------------------
Una descarga se quedó colgada: el fichero `.part` marcaba **117 MB y hora y cuarenta minutos sin
escribir un solo byte**. `yt-dlp` seguía esperando datos de una conexión muerta, y el
`socket_timeout` de 20 s no salta en ese caso (sólo cubre la lectura del socket, no una conexión que
se queda abierta sin enviar nada).

Consecuencias en cadena, todas medidas:

  1. la vuelta del recolector no terminaba (llevaba 2 h 15 min cuando se cortó a mano);
  2. el candado seguía echado, así que el guion rechazaba vueltas nuevas;
  3. la tarea programada de Windows está configurada como `IgnoreNew`: mientras la vuelta colgada
     seguía «en marcha», **las siguientes no se lanzaron** (último resultado del Programador:
     `0x800710E0`, «el operador o administrador ha rechazado la solicitud»);
  4. resultado: **toda la tarde sin descargar ni publicar nada**, y el usuario preguntando por qué no
     bajaban canciones.

El vigilante (`radiov.youtube._vigilante_de_progreso`) mira el reloj: si el fichero no crece en 120
segundos, corta la descarga. Se pierde esa canción (se reintenta en otra vuelta) y se salva el resto.
"""
import time

import pytest

from radiov.youtube import DescargaAtascada, _vigilante_de_progreso


@pytest.fixture
def reloj(monkeypatch):
    """Reloj de mentira: así el test no espera dos minutos de verdad."""
    estado = {"t": 1000.0}
    monkeypatch.setattr(time, "time", lambda: estado["t"])
    return estado


def test_una_descarga_que_avanza_no_se_corta(reloj):
    h = _vigilante_de_progreso()
    for mb in (1, 2, 3, 4):
        h({"status": "downloading", "downloaded_bytes": mb * 1048576})
        reloj["t"] += 5
    # No ha lanzado nada: la descarga iba bien.


def test_una_descarga_parada_se_corta(reloj):
    h = _vigilante_de_progreso()
    h({"status": "downloading", "downloaded_bytes": 1000})
    reloj["t"] += 30
    h({"status": "downloading", "downloaded_bytes": 1000})      # 30 s sin avanzar: aún no
    reloj["t"] += 120
    with pytest.raises(DescargaAtascada):
        h({"status": "downloading", "downloaded_bytes": 1000})  # 150 s: se corta


def test_si_vuelve_a_avanzar_el_contador_se_reinicia(reloj):
    """Un parón corto (buffering) no puede cortar una descarga que luego sigue."""
    h = _vigilante_de_progreso()
    h({"status": "downloading", "downloaded_bytes": 1000})
    reloj["t"] += 100
    h({"status": "downloading", "downloaded_bytes": 2000})      # vuelve a avanzar
    reloj["t"] += 100
    h({"status": "downloading", "downloaded_bytes": 3000})      # y sigue: no se corta


def test_los_estados_que_no_son_descarga_no_cuentan(reloj):
    """`finished`, `error` o el post-procesado (convertir a mp3) no son «estancarse»."""
    h = _vigilante_de_progreso()
    for estado in ("finished", "error"):
        reloj["t"] += 600
        h({"status": estado, "downloaded_bytes": 0})


def test_el_mensaje_dice_cuanto_llevaba(reloj):
    h = _vigilante_de_progreso("sesión larga")
    h({"status": "downloading", "downloaded_bytes": 117 * 1048576})
    reloj["t"] += 200
    with pytest.raises(DescargaAtascada) as e:
        h({"status": "downloading", "downloaded_bytes": 117 * 1048576})
    assert "117.0 MB" in str(e.value)
    assert "sesión larga" in str(e.value)
