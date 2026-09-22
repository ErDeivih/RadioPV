"""Agente del PC para el botón del móvil: recibe órdenes y cuenta cómo está la máquina.

QUÉ HACE
--------
Cada 5 segundos le pregunta al servidor «¿hay algo que hacer?». Si hay una orden, la ejecuta:

    apagar · reiniciar · suspender · cancelar (un apagado que aún no ha empezado)

Y cada 30 segundos manda un «latido» con lo que ve de su propia red (cable de red puesto o no,
wifi, direcciones MAC). Eso es lo que permite que la página del móvil diga **por qué** el botón
de encender no funciona, en vez de dejar al usuario adivinando.

POR QUÉ EL PC PREGUNTA EN VEZ DE ESCUCHAR
-----------------------------------------
Lo natural sería que el servidor llamara al PC («oye, apágate»). No se puede sin tocar nada:
Windows bloquea las conexiones entrantes —comprobado, con el cortafuegos en perfil público no
entra ni un `curl` desde el servidor— y abrir el puerto necesita permisos de administrador, que
este agente no tiene ni quiere. Al revés no hace falta nada: el PC ya habla con el servidor (es
lo que hace el recolector cada 15 minutos), así que aprovecha esa misma conexión.

Y de propina, como es el PC quien habla, puede contar si tiene el cable de red conectado: eso es
justo el dato que hacía falta para entender por qué el botón de encender no hacía nada (el
Wake-on-LAN por wifi no funciona, así que sin cable no hay forma de despertarlo).

CÓMO SE INSTALA (en el PC)
--------------------------
    .venv\\Scripts\\python.exe pc\\agente_boton.py --una-vez     # probar una consulta y salir
    .venv\\Scripts\\python.exe pc\\agente_boton.py               # queda escuchando órdenes

Hay un guion que lo deja programado para que arranque solo al encender el PC:
`pc\\instalar-agente-boton.ps1`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
sys.path.insert(0, str(RAIZ))

#: Bandera de Windows para que los comandos NO abran una ventana negra.
#: Sin esto, cada consulta de red lanzaba un PowerShell visible: el terminal
#: parpadeaba cada pocos segundos y no dejaba trabajar.
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Cada cuánto se pregunta si hay órdenes y cada cuánto se manda el latido.
SEGUNDOS_ENTRE_CONSULTAS = 5
SEGUNDOS_ENTRE_LATIDOS = 30
# Margen que se le da al apagado/reinicio para poder cancelarlo desde el móvil.
SEGUNDOS_DE_AVISO = 20

ORDENES = ("apagar", "reiniciar", "suspender", "cancelar")


def _log(ruta: Path, mensaje: str) -> None:
    """Registro pequeño y con fecha: sin esto, «no hace nada» no se puede investigar."""
    linea = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {mensaje}"
    print(linea, flush=True)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def cargar_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"No encuentro {CONFIG_PATH}")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for clave in ("api", "datos_locales"):
        if not cfg.get(clave):
            sys.exit(f"Falta «{clave}» en {CONFIG_PATH}")
    return cfg


def _pedir(url: str, token: str, *, datos: dict | None = None, timeout: int = 15) -> tuple[dict, str]:
    """Una llamada al servidor. Devuelve (datos, error).

    El error NO se traga a propósito: la primera versión devolvía {} ante cualquier fallo, y como
    «no hay órdenes» también es {}, una dirección mal puesta parecía «todo bien» y el botón del
    móvil no hacía nada sin decir por qué. (Pasó: el agente llamaba al puerto 8090 en vez del 8099
    donde vive el botón, y nadie se enteró hasta mirar el latido que no llegaba.)
    """
    cab = {"X-Ingest-Token": token, "Content-Type": "application/json"}
    try:
        if datos is None:
            req = urllib.request.Request(url, headers=cab)
        else:
            req = urllib.request.Request(url, headers=cab, data=json.dumps(datos).encode(),
                                         method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}"), ""
    except urllib.error.HTTPError as e:
        return {}, f"el servidor contestó {e.code} en {url} (¿boton_url y boton_token correctos?)"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {}, f"no se pudo contactar con {url}: {e}"
    except ValueError as e:
        return {}, f"respuesta ilegible de {url}: {e}"


def estado_de_red() -> dict:
    """Cable de red, wifi y MAC, tal y como los ve Windows.

    Se pregunta con PowerShell porque es la única forma fiable de saber si el cable está puesto
    (una tarjeta desconectada no tiene IP, pero sigue existiendo y es la que puede despertar al
    PC si está conectada).
    """
    orden = ("Get-NetAdapter | Where-Object { $_.Virtual -eq $false } | "
             "Select-Object Name,Status,LinkSpeed,MacAddress | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", orden],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, creationflags=SIN_VENTANA)
        datos = json.loads(r.stdout.strip() or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    if isinstance(datos, dict):
        datos = [datos]
    adaptadores = []
    for a in datos:
        if not isinstance(a, dict):
            continue
        adaptadores.append({"nombre": a.get("Name"), "estado": a.get("Status"),
                            "velocidad": a.get("LinkSpeed"), "mac": a.get("MacAddress")})
    ethernet = next((a for a in adaptadores if (a["nombre"] or "").lower().startswith("ethernet")), None)
    wifi = next((a for a in adaptadores if "wi-fi" in (a["nombre"] or "").lower()
                 or "wifi" in (a["nombre"] or "").lower()), None)
    return {
        "adaptadores": adaptadores,
        "ethernet_conectado": bool(ethernet and ethernet["estado"] == "Up"),
        "ethernet": ethernet,
        "wifi_conectado": bool(wifi and wifi["estado"] == "Up"),
        "wifi": wifi,
    }


def ejecutar(orden: str, probar: bool) -> str:
    """Ejecuta la orden. Devuelve el texto de lo que ha hecho (o habría hecho)."""
    if orden == "apagar":
        cmd = ["shutdown", "/s", "/t", str(SEGUNDOS_DE_AVISO), "/c",
               "Apagando el PC desde el movil (RadioPV)"]
    elif orden == "reiniciar":
        cmd = ["shutdown", "/r", "/t", str(SEGUNDOS_DE_AVISO), "/c",
               "Reiniciando el PC desde el movil (RadioPV)"]
    elif orden == "cancelar":
        cmd = ["shutdown", "/a"]
    elif orden == "suspender":
        # Se suspende con la llamada de .NET porque `rundll32 powrprof.dll,SetSuspendState`
        # HIBERNA cuando la hibernación está activada (y aquí lo está), y desde hibernación el
        # Wake-on-LAN es menos fiable que desde suspensión.
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "Add-Type -AssemblyName System.Windows.Forms; "
               "[System.Windows.Forms.Application]::SetSuspendState('Suspend',$false,$false)"]
    else:
        return f"orden desconocida: {orden}"

    if probar:
        return f"(PRUEBA) habría ejecutado: {' '.join(cmd)}"
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, creationflags=SIN_VENTANA)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"no se pudo ejecutar {orden}: {e}"
    salida = (r.stdout or r.stderr or "").strip()
    return f"{orden}: código {r.returncode}" + (f" · {salida[:120]}" if salida else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Agente del botón del móvil (apagar/reiniciar/suspender).")
    ap.add_argument("--una-vez", action="store_true", help="una consulta al servidor y salir")
    ap.add_argument("--probar", action="store_true",
                    help="no ejecuta nada: sólo cuenta lo que haría (para comprobarlo sin apagar el PC)")
    args = ap.parse_args()

    cfg = cargar_config()
    # OJO: el botón NO vive en la API del recolector (que va bajo /api), sino en su propio
    # servicio, en otro puerto. Por eso hay una clave aparte en `pc/config.json`.
    boton_url = (cfg.get("boton_url") or "").rstrip("/")
    if not boton_url:
        sys.exit("Falta «boton_url» en pc/config.json (por ejemplo http://servidor:8099)")
    boton_token = cfg.get("boton_token") or cfg.get("token", "")
    log = Path(cfg["datos_locales"]) / "boton_pc.log"
    probar = args.probar or bool(cfg.get("boton_probar"))

    if args.una_vez:
        estado = estado_de_red()
        _log(log, f"consulta única · estado de red: {json.dumps(estado, ensure_ascii=False)[:200]}")
        respuesta, error = _pedir(f"{boton_url}/boton/orden?t={boton_token}", boton_token)
        _log(log, f"orden recibida: {respuesta}" + (f" · ERROR: {error}" if error else ""))
        return 0

    _log(log, f"agente del botón en marcha · {boton_url}"
              + (" · MODO PRUEBA (no ejecuta nada)" if probar else ""))
    ultimo_latido = 0.0
    while True:
        try:
            ahora = time.time()
            if ahora - ultimo_latido >= SEGUNDOS_ENTRE_LATIDOS:
                estado = estado_de_red()
                estado["probar"] = probar
                _datos, error = _pedir(f"{boton_url}/boton/latido?t={boton_token}", boton_token,
                                       datos=estado)
                if error:
                    _log(log, f"latido no entregado · {error}")
                ultimo_latido = ahora

            respuesta, error = _pedir(f"{boton_url}/boton/orden?t={boton_token}", boton_token)
            if error:
                _log(log, f"no se pudo preguntar por órdenes · {error}")
            orden = (respuesta or {}).get("orden") or ""
            if orden and orden in ORDENES:
                hecho = ejecutar(orden, probar)
                _log(log, f"orden «{orden}» · {hecho}")
                _pedir(f"{boton_url}/boton/hecho?t={boton_token}", boton_token,
                       datos={"orden": orden, "resultado": hecho})
        except Exception as e:  # noqa: BLE001  (el agente no puede morirse nunca por un fallo)
            _log(log, f"error: {e}")
        time.sleep(SEGUNDOS_ENTRE_CONSULTAS)


if __name__ == "__main__":
    sys.exit(main())
