"""Regenera el logo de RadioPV SIN las tres lineas de Spotify, y todos los iconos de la PWA.

Que se hace y por que
---------------------
El logo era un circulo verde con la cara y, debajo, **las tres lineas curvas de Spotify**, que
ademas tapaban parte del cuello. Borrarlas con un pincel del mismo color no vale: la primera
linea cruza el cuello, asi que quedaria un parche visible.

Como el fondo es VERDE PLANO, lo limpio es reconstruirlo: se recorta la cara por encima de donde
empiezan las lineas (y=730, medido sobre la imagen), se coloca centrada sobre un circulo verde
nuevo y se recorta en circulo. Asi no queda ni rastro de las lineas y la cara no se deforma.

Uso:  python scripts/logo_sin_lineas.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "_deploy" / "_logo" / "logo_final.png"
PUBLICO = RAIZ / "frontend" / "public"

# Medido sobre la imagen original (1024x1024):
#   - el fondo es verde plano #1DB954;
#   - la cara (gorra incluida) va de x=262 a x=768;
#   - las tres lineas empiezan en y=730 (los extremos) y el centro baja mas.
CORTE_Y = 704
CARA_X0, CARA_X1 = 262, 768
VERDE = (29, 185, 84)

TAM = 1024
ALTO_CARA = 900          # deja una banda verde arriba y abajo, como el original


def circulo(imagen: Image.Image, lado: int) -> Image.Image:
    """Recorta la imagen en circulo (el resto, transparente)."""
    lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    mascara = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, lado - 1, lado - 1), fill=255)
    lienzo.paste(imagen, (0, 0), mascara)
    return lienzo


def construir_cara() -> Image.Image:
    """Devuelve la cara recortada y escalada, lista para pegar sobre el circulo verde."""
    original = Image.open(ORIGEN).convert("RGBA")
    # 1) fuera las lineas: se recorta por encima de donde empiezan
    cara = original.crop((CARA_X0, 0, CARA_X1, CORTE_Y))
    # 2) se escala manteniendo la proporcion (nada de deformar la cara)
    factor = ALTO_CARA / cara.height
    nuevo = (max(1, round(cara.width * factor)), ALTO_CARA)
    return cara.resize(nuevo, Image.LANCZOS)


def logo(lado: int = TAM, margen_extra: float = 0.0) -> Image.Image:
    """Logo cuadrado: circulo verde + la cara centrada. `margen_extra` sirve para los iconos
    'maskable', que necesitan el contenido dentro del 80 % central porque Android los recorta."""
    escala = 1.0 - margen_extra
    cara = construir_cara()
    if escala != 1.0:
        cara = cara.resize((round(cara.width * escala), round(cara.height * escala)), Image.LANCZOS)

    lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    # circulo verde
    ImageDraw.Draw(lienzo).ellipse((0, 0, lado - 1, lado - 1), fill=VERDE + (255,))
    # la cara, centrada horizontalmente y con una banda verde arriba y abajo
    x = (lado - cara.width) // 2
    y = (lado - cara.height) // 2
    lienzo.alpha_composite(cara, (x, y))
    return circulo(lienzo, lado)


def guardar(im: Image.Image, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    im.save(ruta)
    print(f"   {ruta.relative_to(RAIZ)}  {im.size[0]}x{im.size[1]}")


def main() -> int:
    if not ORIGEN.exists():
        print(f"[ERROR] no esta el original: {ORIGEN}")
        return 1

    base = logo(TAM)
    guardar(base, PUBLICO / "logo.png")
    guardar(base.resize((512, 512), Image.LANCZOS), PUBLICO / "icon-512.png")
    guardar(base.resize((192, 192), Image.LANCZOS), PUBLICO / "icon-192.png")
    guardar(base.resize((64, 64), Image.LANCZOS), PUBLICO / "favicon-64.png")
    guardar(base.resize((32, 32), Image.LANCZOS), PUBLICO / "favicon32.png")
    guardar(base.resize((16, 16), Image.LANCZOS), PUBLICO / "favicon16.png")

    # Maskable: Android recorta el borde, asi que el contenido va mas pequeño (80 % central).
    maskable = logo(TAM, margen_extra=0.22)
    guardar(maskable.resize((512, 512), Image.LANCZOS), PUBLICO / "icon-maskable-512.png")
    guardar(maskable.resize((192, 192), Image.LANCZOS), PUBLICO / "icon-maskable-192.png")

    # iOS no admite transparencia en el icono de inicio: va a sangre, cuadrado y sin alfa.
    apple = Image.new("RGB", (180, 180), VERDE)
    chico = logo(1024).resize((180, 180), Image.LANCZOS)
    apple.paste(chico, (0, 0), chico)
    guardar(apple, PUBLICO / "apple-touch-icon.png")

    # favicon.ico con varios tamaños
    base.save(PUBLICO / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f"   frontend/public/favicon.ico  (16, 32, 48, 64)")

    print("\n[OK] logo e iconos regenerados SIN las tres lineas de Spotify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
