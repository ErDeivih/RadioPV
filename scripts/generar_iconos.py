"""Genera el juego completo de iconos de RadioNano a partir del logo elegido.

Logo: mezcla de Spotify (el disco verde y los tres arcos) con la cara recortada. Variante
elegida: cara grande y los tres arcos anchos abajo.

Detalle importante de los iconos de PWA: en `manifest.json` los PNG venian marcados como
`purpose: "any maskable"`, y Android recorta los maskable a un circulo o un cuadrado
redondeado. Un logo circular con las esquinas TRANSPARENTES se veria con las esquinas
negras al recortarlo. Por eso se generan dos juegos:
  · icon-*.png            -> el logo circular, purpose "any"
  · icon-maskable-*.png   -> disco verde a sangre (sin transparencia) y el contenido
                             reducido al 74%, que es la zona segura del recorte

Uso:
    python scripts/generar_iconos.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generar_logo import VERDE, variante_final  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
BASE = RAIZ / "_deploy" / "_logo"
PUBLIC = RAIZ / "frontend" / "public"

CARA = BASE / "cara1_cap_recorte.png"     # la cara de la gorra: mas contraste
VARIANTE = 21


def logo_circular(lado: int) -> Image.Image:
    return variante_final(VARIANTE, CARA, lado)


def maskable(lado: int) -> Image.Image:
    """Disco verde a sangre con el contenido dentro de la zona segura del recorte."""
    fondo = Image.new("RGBA", (lado, lado), VERDE + (255,))
    interior = logo_circular(int(lado * 0.74))
    fondo.alpha_composite(interior, ((lado - interior.width) // 2,
                                     (lado - interior.height) // 2))
    # Sobre fondo opaco: sin nada transparente, para que el recorte no deje huecos.
    return fondo.convert("RGB")


def manzana(lado: int) -> Image.Image:
    """apple-touch-icon: iOS tambien recorta y no admite transparencia."""
    return maskable(lado)


def guardar(im: Image.Image, ruta: Path) -> None:
    im.save(ruta)
    print(f"    {ruta.name:<26} {im.size[0]}x{im.size[1]}  {ruta.stat().st_size/1024:.1f} KB")


def main() -> int:
    if not CARA.exists():
        print(f"  [X] falta {CARA}. Ejecuta antes scripts/recortar_caras.py")
        return 1

    print("  generando el logo a alta resolucion...")
    grande = logo_circular(1024)

    print("  guardando en frontend/public/:")
    guardar(grande, PUBLIC / "logo.png")
    guardar(logo_circular(512), PUBLIC / "icon-512.png")
    guardar(logo_circular(192), PUBLIC / "icon-192.png")
    guardar(logo_circular(64), PUBLIC / "favicon-64.png")
    guardar(logo_circular(32), PUBLIC / "favicon32.png")
    guardar(logo_circular(16), PUBLIC / "favicon16.png")
    guardar(maskable(512), PUBLIC / "icon-maskable-512.png")
    guardar(maskable(192), PUBLIC / "icon-maskable-192.png")
    guardar(manzana(180), PUBLIC / "apple-touch-icon.png")

    # .ico multitamaño: Windows y algunos navegadores lo prefieren.
    ico = logo_circular(256)
    ico.save(PUBLIC / "favicon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
    print(f"    favicon.ico                16..64  {(PUBLIC / 'favicon.ico').stat().st_size/1024:.1f} KB")

    # Copia del logo a alta resolucion, por si hace falta luego.
    grande.save(BASE / "logo_final.png")
    print(f"\n  original a 1024 px: {BASE / 'logo_final.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
