"""Corrector del catálogo: revisa las canciones una a una y corrige lo que esté mal.

Por defecto **no toca nada**: enseña lo que encuentra y lo que propondría cambiar. Para que
escriba de verdad hay que pasar `--apply`.

Uso:
    # ver qué encuentra en 20 canciones, sin tocar nada
    .venv\\Scripts\\python.exe scripts\\corregir_catalogo.py --limit 20

    # revisar las que ya salieron mal o dudosas
    .venv\\Scripts\\python.exe scripts\\corregir_catalogo.py --solo-dudosos --limit 50

    # aplicar las correcciones de metadatos (no sustituye ficheros)
    .venv\\Scripts\\python.exe scripts\\corregir_catalogo.py --limit 50 --apply

    # sin audio ni YouTube: mucho más rápido, pero se le escapan las covers
    .venv\\Scripts\\python.exe scripts\\corregir_catalogo.py --limit 200 --sin-audio --sin-youtube

Opciones útiles:
    --json informe.json     guarda el informe completo
    --con-audio-solo N      limita el análisis de audio a las N primeras (es lo más lento)
    --veredicto X           revisa solo las que tengan ese veredicto
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from radiov import corrector as CO  # noqa: E402

COLORES = {
    CO.CORRECTA: "\033[92m",       # verde
    CO.METADATOS: "\033[93m",      # amarillo
    CO.OTRA_VERSION: "\033[95m",   # magenta
    CO.OTRA_CANCION: "\033[91m",   # rojo
    CO.FICHERO_MAL: "\033[91m",    # rojo
    CO.DUDOSO: "\033[96m",         # cian
    CO.SIN_DATOS: "\033[90m",      # gris
}
FIN = "\033[0m"

ETIQUETA = {
    CO.CORRECTA: "correcta",
    CO.METADATOS: "datos mal",
    CO.OTRA_VERSION: "OTRA VERSIÓN",
    CO.OTRA_CANCION: "OTRA CANCIÓN",
    CO.FICHERO_MAL: "fichero mal",
    CO.DUDOSO: "dudoso",
    CO.SIN_DATOS: "sin datos",
}


def color(veredicto: str, texto: str, activo: bool = True) -> str:
    if not activo:
        return texto
    return f"{COLORES.get(veredicto, '')}{texto}{FIN}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Revisa y corrige el catálogo canción a canción.")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--apply", action="store_true",
                    help="escribe las correcciones (por defecto solo revisa y apunta el veredicto)")
    ap.add_argument("--no-recordar", action="store_true",
                    help="no escribe NADA, ni el veredicto (pasada totalmente limpia)")
    ap.add_argument("--reemplazar", action="store_true",
                    help="además de corregir datos, vuelve a DESCARGAR las canciones cuyo "
                         "fichero esté mal (el viejo se aparta en _descartes, no se borra)")
    ap.add_argument("--solo-dudosos", action="store_true",
                    help="solo las ya marcadas como dudosas o nunca revisadas")
    ap.add_argument("--veredicto", default=None, help="revisar solo las de este veredicto")
    ap.add_argument("--sin-audio", action="store_true", help="no comparar el audio (rápido)")
    ap.add_argument("--sin-youtube", action="store_true", help="no buscar en YouTube (rápido)")
    ap.add_argument("--horas", type=int, default=0,
                    help="revisar también las verificadas hace más de N horas")
    ap.add_argument("--json", default=None, help="guardar el informe en este fichero")
    ap.add_argument("--detallado", action="store_true", help="imprime todos los detalles")
    ap.add_argument("--sin-color", action="store_true")
    args = ap.parse_args()

    tty = not args.sin_color and sys.stdout.isatty()

    print("=" * 78)
    print("  CORRECTOR DEL CATÁLOGO")
    print(f"  modo: {'APLICANDO CAMBIOS' if args.apply else 'solo informar (añade --apply para escribir)'}")
    print(f"  comprobaciones: fichero · etiquetas ID3 · Deezer"
          f"{' · audio' if not args.sin_audio else ''}"
          f"{' · YouTube' if not args.sin_youtube else ''}")
    print("=" * 78)

    if args.veredicto:
        lote = CO.pendientes(args.limit, incluir_veredictos=[args.veredicto], horas=args.horas)
    else:
        lote = CO.pendientes(args.limit, solo_dudosos=args.solo_dudosos, horas=args.horas)
    if not lote:
        print("\n  No hay canciones pendientes de revisar. Usa --horas N para repasar las ya vistas.")
        return 0

    print(f"\n  {len(lote)} canción(es) a revisar\n")

    from radiov import deezer as dz
    try:
        cliente = dz.DeezerClient()
    except Exception:  # noqa: BLE001
        cliente = None

    analisis: list[CO.Analisis] = []
    conteo: Counter = Counter()
    t0 = time.time()

    for i, t in enumerate(lote, 1):
        etiqueta = f"{t.get('artist')} - {t.get('title')}"
        inicio = time.time()
        try:
            a = CO.analizar(t, client=cliente, con_audio=not args.sin_audio,
                            con_youtube=not args.sin_youtube)
        except Exception as e:  # noqa: BLE001
            a = CO.Analisis(track_id=int(t["id"]), titulo=t.get("title") or "",
                            artista=t.get("artist") or "", veredicto=CO.SIN_DATOS,
                            problemas=[f"error inesperado: {type(e).__name__}: {e}"])
        a.detalle["_track"] = t
        analisis.append(a)
        conteo[a.veredicto] += 1

        dur = time.time() - inicio
        aud = a.detalle.get("audio") or {}
        marcas = ""
        if aud.get("ok"):
            marcas = f"  croma={aud['croma']:.2f} mfcc={aud['mfcc']:.2f}"
        print(f"  {i:>4}. {color(a.veredicto, f'{ETIQUETA[a.veredicto]:<13}', tty)}"
              f" {etiqueta[:48]:<48} ({dur:.1f}s){marcas}")
        for p in a.problemas[:3 if not args.detallado else 99]:
            print(f"        · {p}")
        if a.correcciones:
            campos = ", ".join(f"{k}={v!r}" for k, v in list(a.correcciones.items())[:6])
            print(f"        {'escribiría' if not args.apply else 'escrito'}: {campos}")
        if args.apply:
            hecho = CO.aplicar(a)
            if hecho.get("fichero_movido"):
                print(f"        fichero recolocado en: {hecho['fichero_movido']}")
            for k in ("error_tags", "error_mover"):
                if hecho.get(k):
                    print(f"        [X] {k}: {hecho[k]}")
        elif not args.no_recordar:
            # Se apunta el veredicto (sin tocar la ficha) para que la próxima pasada siga
            # por donde iba en vez de volver a empezar por las mismas canciones.
            CO.registrar(a)

        if args.reemplazar and a.veredicto in CO.NECESITAN_DESCARGA:
            print(f"        reemplazando el fichero (veredicto {a.veredicto})...")
            try:
                r = CO.reemplazar_fichero(t, a)
            except Exception as e:  # noqa: BLE001
                r = {"error": f"{type(e).__name__}: {e}"}
            for paso in r.get("pasos", []):
                print(f"          · {paso}")
            if r.get("error"):
                print(f"          [X] {r['error']}")
            if r.get("reemplazado"):
                print(f"          -> FICHERO SUSTITUIDO "
                      f"(el viejo en {r.get('viejo_apartado') or 'no había'})")

    total = time.time() - t0
    print("\n" + "=" * 78)
    print(f"  RESUMEN · {len(analisis)} canciones en {total/60:.1f} min "
          f"({total/max(len(analisis),1):.1f}s cada una)")
    print("=" * 78)
    for v in CO.VEREDICTOS:
        if conteo.get(v):
            print(f"    {color(v, ETIQUETA[v].ljust(14), tty)} {conteo[v]:>5}")
    con_cambios = sum(1 for a in analisis if a.correcciones)
    print(f"\n    con correcciones de datos : {con_cambios}")
    print(f"    que necesitan descarga    : "
          f"{sum(conteo.get(v, 0) for v in CO.NECESITAN_DESCARGA)}")

    if args.json:
        ruta = Path(args.json)
        ruta.write_text(json.dumps([a.a_dict() for a in analisis], ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print(f"\n    informe guardado en {ruta}")

    if not args.apply:
        if args.no_recordar:
            print("\n    (pasada totalmente limpia: no se ha escrito NADA)")
        else:
            print("\n    Cada canción queda marcada con su veredicto para que la próxima "
                  "pasada siga por donde iba.")
            print("    Para escribir además las correcciones de datos: --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
