"""Recorta las caras de las dos imagenes y las deja con fondo transparente de verdad.

Las imagenes originales son RGB (sin canal alfa): el damero de transparencia esta PINTADO
dentro, con dos grises muy claros (blanco ~254 y gris ~243).

Tres trampas, y como se resuelven:

1. **Los dientes son casi blancos**, igual que el fondo. Una mascara por umbral los deja
   transparentes y agujerea la boca. -> Despues de calcularla se rellena cada fila entre el
   primer y el ultimo pixel de cara.

2. **El borde queda con una franja clara**. Los pixeles justo en el limite son una mezcla
   de cara y fondo; con una mascara binaria se quedan dentro y sale un halo blanco. ->
   Se erosiona la mascara unos pixeles y se suaviza el borde.

3. **El borde queda escalonado** (sin antialias). -> El alfa de la franja de borde se
   calcula de forma continua, segun cuanto se parece el pixel al fondo.

Uso:
    python scripts/recortar_caras.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

BASE = Path(__file__).resolve().parent.parent / "_deploy" / "_logo"
ENTRADAS = {
    "cara1_cap": BASE / "cara1_cap.png",
    "cara2_pelo": BASE / "cara2_pelo.png",
}

EROSION = 4          # pixeles que se recortan del borde para comerse la franja clara
SUAVIZADO = 1.0      # radio del desenfoque del borde


def alfa(im: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (alfa continuo 0..1, silueta dura)."""
    a = np.array(im).astype(np.float32)
    canal_min = a.min(axis=-1)
    croma = a.max(axis=-1) - a.min(axis=-1)

    # Cuanto se aparta el pixel del fondo claro y neutro. 0 = fondo, 1 = claramente cara.
    por_oscuridad = np.clip((255.0 - canal_min - 14.0) / 24.0, 0.0, 1.0)
    por_color = np.clip((croma - 8.0) / 24.0, 0.0, 1.0)
    blando = np.maximum(por_oscuridad, por_color)

    duro = blando > 0.35

    # Quitar filas y columnas con muy pocos pixeles (ruido del JPEG).
    for _ in range(2):
        duro[duro.sum(axis=1) <= 6, :] = False
        duro[:, duro.sum(axis=0) <= 6] = False

    # Relleno por filas: cierra los huecos interiores (dientes, brillos).
    for y in np.where(duro.any(axis=1))[0]:
        cols = np.where(duro[y])[0]
        if len(cols):
            duro[y, cols[0]:cols[-1] + 1] = True

    # Erosion: se come la franja mezclada del borde, que es la que hacia el halo claro.
    if EROSION > 0:
        tmp = Image.fromarray((duro * 255).astype(np.uint8))
        tmp = tmp.filter(ImageFilter.MinFilter(EROSION * 2 + 1))
        duro = np.array(tmp) > 127

    # El alfa final: 1 en el interior, y en la franja de borde el valor continuo.
    interior = Image.fromarray((duro * 255).astype(np.uint8)) \
        .filter(ImageFilter.MinFilter(EROSION * 2 + 5))
    interior = np.array(interior) > 127
    franja = duro & ~interior

    alfa_final = duro.astype(np.float32)
    alfa_final[franja] = np.clip(blando[franja] * 1.25, 0.0, 1.0)
    alfa_final[~duro] = 0.0

    # Suavizado final del contorno, para que no queden escalones.
    if SUAVIZADO > 0:
        img = Image.fromarray((alfa_final * 255).astype(np.uint8))
        img = img.filter(ImageFilter.GaussianBlur(SUAVIZADO))
        alfa_final = np.array(img).astype(np.float32) / 255.0

    return alfa_final, duro


def recortar(nombre: str, ruta: Path) -> None:
    im = Image.open(ruta).convert("RGB")
    a, duro = alfa(im)

    filas = np.where(duro.any(axis=1))[0]
    columnas = np.where(duro.any(axis=0))[0]
    if not len(filas) or not len(columnas):
        print(f"  [X] {nombre}: no se detecto la cara")
        return
    y0, y1 = int(filas[0]), int(filas[-1]) + 1
    x0, x1 = int(columnas[0]), int(columnas[-1]) + 1
    print(f"  {nombre}: cara en x={x0}..{x1}  y={y0}..{y1}  ({x1-x0}x{y1-y0} px)")

    rgba = im.convert("RGBA")
    rgba.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    recorte = rgba.crop((x0, y0, x1, y1))

    lado = max(recorte.size)
    cuadrado = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    cuadrado.paste(recorte, ((lado - recorte.width) // 2, (lado - recorte.height) // 2))
    cuadrado.save(BASE / f"{nombre}_recorte.png")

    # Previsualizacion: sobre claro, sobre oscuro y sobre verde (el fondo real del logo).
    prev = Image.new("RGB", (lado * 3 + 40, lado + 20), (128, 0, 128))
    for i, color in enumerate(((245, 245, 245), (25, 25, 25), (29, 185, 84))):
        fondo = Image.new("RGB", (lado, lado), color)
        fondo.paste(cuadrado, (0, 0), cuadrado)
        prev.paste(fondo, (10 + i * (lado + 10), 10))
    prev.thumbnail((1200, 420))
    prev.save(BASE / f"{nombre}_prev.png")
    print(f"    -> {nombre}_recorte.png + {nombre}_prev.png")


def main() -> int:
    for nombre, ruta in ENTRADAS.items():
        if not ruta.exists():
            print(f"  [X] falta {ruta}")
            continue
        recortar(nombre, ruta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
