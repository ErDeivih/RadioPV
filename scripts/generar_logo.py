"""Genera variantes del logo de RadioNano: mezcla de Spotify con la cara recortada.

Spotify aporta lo reconocible: el disco verde y los tres arcos. La gracia esta en como
conviven con la cara, y eso solo se decide mirandolo, asi que este script dibuja varias
variantes en una rejilla para poder compararlas de un vistazo.

Uso:
    python scripts/generar_logo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BASE = Path(__file__).resolve().parent.parent / "_deploy" / "_logo"
VERDE = (29, 185, 84)          # el verde de Spotify
VERDE_OSCURO = (18, 130, 58)
NEGRO = (17, 17, 17)
BLANCO = (255, 255, 255)

SS = 4                          # supermuestreo, para bordes suaves


def arco(d: ImageDraw.ImageDraw, cx: float, cy: float, ancho_total: float,
         altura: float, y: float, grosor: float, color) -> None:
    """Un arco tipo Spotify: sube por el centro y baja en los extremos."""
    pasos = 120
    puntos = []
    for i in range(pasos + 1):
        t = i / pasos                       # 0..1
        x = cx - ancho_total / 2 + ancho_total * t
        # parabola: 0 en los extremos, -altura en el centro
        yy = y - altura * (1 - (2 * t - 1) ** 2)
        puntos.append((x, yy))
    d.line(puntos, fill=color, width=int(grosor), joint="curve")
    # Extremos redondeados
    for (px, py) in (puntos[0], puntos[-1]):
        r = grosor / 2
        d.ellipse([px - r, py - r, px + r, py + r], fill=color)


def arcos_spotify(d: ImageDraw.ImageDraw, cx: float, cy: float, R: float,
                  grosor: float, color, escala: float = 1.0) -> None:
    """Los tres arcos, apilados y de anchura decreciente."""
    g = grosor * escala
    arco(d, cx, cy, 1.16 * R * escala, 0.30 * R * escala, cy - 0.16 * R, g, color)
    arco(d, cx, cy, 0.92 * R * escala, 0.24 * R * escala, cy + 0.02 * R, g, color)
    arco(d, cx, cy, 0.68 * R * escala, 0.18 * R * escala, cy + 0.20 * R, g, color)


def cara_circular(ruta: Path, lado: int, zoom: float = 1.0,
                  desplazar_y: float = 0.0, ss: int = SS) -> Image.Image:
    """Devuelve la cara recortada en un circulo transparente de 'lado' pixeles.

    `ss` es el supermuestreo de la mascara del circulo. Si ya se esta dibujando a alta
    resolucion conviene pasarle 1, porque si no se multiplica por 4 otra vez y se dispara
    el consumo de memoria sin ganar nada.
    """
    cara = Image.open(ruta).convert("RGBA")
    # Ajustar para que la cara llene el circulo (zoom > 1 recorta mas)
    objetivo = int(lado * zoom)
    escala = objetivo / max(cara.size)
    nuevo = (max(1, int(cara.width * escala)), max(1, int(cara.height * escala)))
    cara = cara.resize(nuevo, Image.LANCZOS)

    lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    dx = (lado - cara.width) // 2
    dy = (lado - cara.height) // 2 + int(lado * desplazar_y)
    lienzo.paste(cara, (dx, dy), cara)

    if ss > 1:
        mascara = Image.new("L", (lado * ss, lado * ss), 0)
        ImageDraw.Draw(mascara).ellipse([0, 0, lado * ss - 1, lado * ss - 1], fill=255)
        mascara = mascara.resize((lado, lado), Image.LANCZOS)
    else:
        mascara = Image.new("L", (lado, lado), 0)
        ImageDraw.Draw(mascara).ellipse([0, 0, lado - 1, lado - 1], fill=255)
    lienzo.putalpha(Image.composite(lienzo.getchannel("A"), Image.new("L", (lado, lado), 0),
                                    mascara))
    return lienzo


def disco(lado: int, color=VERDE) -> Image.Image:
    im = Image.new("RGBA", (lado * SS, lado * SS), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([0, 0, lado * SS - 1, lado * SS - 1], fill=color)
    return im.resize((lado, lado), Image.LANCZOS)


def arcos_repartidos(d: ImageDraw.ImageDraw, cx: float, cy: float, R: float,
                     grosor: float, color) -> None:
    """Los tres arcos REPARTIDOS por todo el disco, no apilados en el centro.

    Es la clave para que la cara y los arcos no se peleen: asi el arco de arriba asoma
    sobre la cabeza, el de abajo bajo la barbilla, y el del medio saca los extremos a los
    lados. Si se apilan en el centro, la cara los tapa y solo quedan dos muñones negros
    a la altura de las orejas, que parece que el tio lleva alas.
    """
    arco(d, cx, cy, 1.44 * R, 0.30 * R, cy - 0.60 * R, grosor, color)
    arco(d, cx, cy, 1.62 * R, 0.26 * R, cy + 0.00 * R, grosor, color)
    arco(d, cx, cy, 1.44 * R, 0.30 * R, cy + 0.60 * R, grosor, color)


def variante(numero: int, cara: Path, lado: int = 512) -> Image.Image:
    R = lado / 2
    cx = cy = R

    if numero == 7:
        # Arcos repartidos (negros) + cara en circulo centrada
        im = disco(lado)
        d = ImageDraw.Draw(im)
        arcos_repartidos(d, cx, cy, R, R * 0.105, NEGRO)
        f = cara_circular(cara, int(lado * 0.56), zoom=1.02)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        return im

    if numero == 8:
        # Igual pero arcos blancos, mas legibles sobre el verde
        im = disco(lado, (18, 140, 62))
        d = ImageDraw.Draw(im)
        arcos_repartidos(d, cx, cy, R, R * 0.10, BLANCO)
        f = cara_circular(cara, int(lado * 0.56), zoom=1.02)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        return im

    if numero == 9:
        # Cara algo mayor y con anillo blanco, arcos repartidos
        im = disco(lado, (18, 140, 62))
        d = ImageDraw.Draw(im)
        arcos_repartidos(d, cx, cy, R, R * 0.10, BLANCO)
        diam = int(lado * 0.58)
        d.ellipse([(lado - diam) / 2 - lado * 0.010, (lado - diam) / 2 - lado * 0.010,
                   (lado + diam) / 2 + lado * 0.010, (lado + diam) / 2 + lado * 0.010],
                  fill=BLANCO)
        f = cara_circular(cara, diam, zoom=1.02)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        return im

    if numero == 10:
        # La cara llena el disco (es el logo) y los arcos van debajo, fuera de la cara
        im = disco(lado)
        f = cara_circular(cara, int(lado * 0.80), zoom=1.0, desplazar_y=-0.06)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        d = ImageDraw.Draw(im)
        arco(d, cx, cy, 1.00 * R, 0.16 * R, cy + 0.66 * R, R * 0.085, NEGRO)
        arco(d, cx, cy, 0.72 * R, 0.13 * R, cy + 0.80 * R, R * 0.085, NEGRO)
        return im

    if numero == 11:
        # Cara llenando el disco, sin arcos: solo el verde y el circulo (minimalista)
        im = disco(lado)
        f = cara_circular(cara, int(lado * 0.80), zoom=1.0)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        return im

    # numero == 12: cara grande + los tres arcos como corona arriba
    im = disco(lado)
    f = cara_circular(cara, int(lado * 0.82), zoom=1.0, desplazar_y=0.05)
    im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
    d = ImageDraw.Draw(im)
    arco(d, cx, cy, 1.05 * R, 0.13 * R, cy - 0.72 * R, R * 0.075, NEGRO)
    arco(d, cx, cy, 0.82 * R, 0.11 * R, cy - 0.56 * R, R * 0.075, NEGRO)
    return im


def variante_final(numero: int, cara: Path, lado: int = 512) -> Image.Image:
    """Afinado de la ganadora: cara grande y los tres arcos anchos abajo.

    Todo se dibuja a 4x y se reduce al final. Es imprescindible para los arcos: `ImageDraw`
    no aplica antialias a las lineas gruesas, asi que a resolucion final salen con el borde
    dentado. Dibujando grande y reduciendo con LANCZOS, quedan limpios.
    """
    S = lado * 4
    R = S / 2
    cx = cy = R

    def base(escala_cara: float, dy: float, color=VERDE):
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse([0, 0, S - 1, S - 1], fill=color)
        f = cara_circular(cara, int(S * escala_cara), zoom=1.0, desplazar_y=dy, ss=1)
        im.alpha_composite(f, ((S - f.width) // 2, (S - f.height) // 2))
        return im

    def tres_arcos(im, ancho_medio: float, grosor: float, color=NEGRO, y0=0.56):
        d = ImageDraw.Draw(im)
        arco(d, cx, cy, ancho_medio * R, 0.15 * R, cy + y0 * R, grosor, color)
        arco(d, cx, cy, ancho_medio * 0.78 * R, 0.13 * R, cy + (y0 + 0.16) * R, grosor, color)
        arco(d, cx, cy, ancho_medio * 0.57 * R, 0.10 * R, cy + (y0 + 0.30) * R, grosor, color)
        return im

    if numero == 19:
        im = tres_arcos(base(0.74, -0.05), 1.30, R * 0.070)
    elif numero == 20:
        im = tres_arcos(base(0.78, -0.07), 1.30, R * 0.070)
    elif numero == 21:
        im = tres_arcos(base(0.80, -0.09), 1.34, R * 0.062)
    elif numero == 22:
        im = tres_arcos(base(0.74, -0.05), 1.30, R * 0.070, color=BLANCO, y0=0.56)
    elif numero == 23:
        im = tres_arcos(base(0.80, -0.09), 1.34, R * 0.062, color=BLANCO)
    else:
        # 24: la cara mas grande y solo dos arcos (menos ruido a tamaño pequeño)
        im = base(0.84, -0.12)
        d = ImageDraw.Draw(im)
        arco(d, cx, cy, 1.30 * R, 0.15 * R, cy + 0.62 * R, R * 0.072, NEGRO)
        arco(d, cx, cy, 0.98 * R, 0.12 * R, cy + 0.79 * R, R * 0.072, NEGRO)

    return im.resize((lado, lado), Image.LANCZOS)


def variante_v3(numero: int, cara: Path, lado: int = 512) -> Image.Image:
    """Tercera ronda: cara grande (que es lo que se reconoce) y los arcos abajo."""
    R = lado / 2
    cx = cy = R

    if numero == 13:
        # Cara 0.80 arriba + TRES arcos negros abajo
        im = disco(lado)
        f = cara_circular(cara, int(lado * 0.80), zoom=1.0, desplazar_y=-0.08)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        d = ImageDraw.Draw(im)
        arco(d, cx, cy, 1.06 * R, 0.13 * R, cy + 0.60 * R, R * 0.072, NEGRO)
        arco(d, cx, cy, 0.84 * R, 0.11 * R, cy + 0.74 * R, R * 0.072, NEGRO)
        arco(d, cx, cy, 0.62 * R, 0.09 * R, cy + 0.86 * R, R * 0.072, NEGRO)
        return im

    if numero == 14:
        # Igual que la 13 pero con los arcos en blanco y verde mas oscuro
        im = disco(lado, (18, 140, 62))
        f = cara_circular(cara, int(lado * 0.80), zoom=1.0, desplazar_y=-0.08)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        d = ImageDraw.Draw(im)
        arco(d, cx, cy, 1.06 * R, 0.13 * R, cy + 0.60 * R, R * 0.075, BLANCO)
        arco(d, cx, cy, 0.84 * R, 0.11 * R, cy + 0.74 * R, R * 0.075, BLANCO)
        arco(d, cx, cy, 0.62 * R, 0.09 * R, cy + 0.86 * R, R * 0.075, BLANCO)
        return im

    if numero == 15:
        # Cara algo menor (0.72): mas verde alrededor y arcos mas holgados
        im = disco(lado)
        f = cara_circular(cara, int(lado * 0.72), zoom=1.02, desplazar_y=-0.05)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        d = ImageDraw.Draw(im)
        arco(d, cx, cy, 1.16 * R, 0.14 * R, cy + 0.52 * R, R * 0.078, NEGRO)
        arco(d, cx, cy, 0.92 * R, 0.12 * R, cy + 0.68 * R, R * 0.078, NEGRO)
        arco(d, cx, cy, 0.68 * R, 0.10 * R, cy + 0.82 * R, R * 0.078, NEGRO)
        return im

    if numero == 16:
        # Los arcos ARRIBA y la cara abajo (mirando hacia arriba)
        im = disco(lado)
        f = cara_circular(cara, int(lado * 0.80), zoom=1.0, desplazar_y=0.08)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        d = ImageDraw.Draw(im)
        arco(d, cx, cy, 1.02 * R, 0.13 * R, cy - 0.58 * R, R * 0.072, NEGRO)
        arco(d, cx, cy, 0.80 * R, 0.11 * R, cy - 0.72 * R, R * 0.072, NEGRO)
        return im

    if numero == 17:
        # La cara SIN recortar en circulo: la silueta de la cabeza sobre el disco verde
        im = disco(lado, VERDE_OSCURO)
        cara_img = Image.open(cara).convert("RGBA")
        escala = (lado * 0.94) / max(cara_img.size)
        cara_img = cara_img.resize(
            (max(1, int(cara_img.width * escala)), max(1, int(cara_img.height * escala))),
            Image.LANCZOS)
        im.alpha_composite(cara_img,
                           ((lado - cara_img.width) // 2,
                            (lado - cara_img.height) // 2 - int(lado * 0.03)))
        d = ImageDraw.Draw(im)
        arco(d, cx, cy, 1.00 * R, 0.12 * R, cy + 0.66 * R, R * 0.070, BLANCO)
        arco(d, cx, cy, 0.78 * R, 0.10 * R, cy + 0.80 * R, R * 0.070, BLANCO)
        return im

    # numero == 18: como la 13 pero el arco del medio mas largo (mas Spotify)
    im = disco(lado)
    f = cara_circular(cara, int(lado * 0.78), zoom=1.0, desplazar_y=-0.09)
    im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
    d = ImageDraw.Draw(im)
    arco(d, cx, cy, 1.30 * R, 0.15 * R, cy + 0.56 * R, R * 0.070, NEGRO)
    arco(d, cx, cy, 1.02 * R, 0.13 * R, cy + 0.72 * R, R * 0.070, NEGRO)
    arco(d, cx, cy, 0.74 * R, 0.10 * R, cy + 0.86 * R, R * 0.070, NEGRO)
    return im


def variante_v1(numero: int, cara: Path, lado: int = 512) -> Image.Image:
    """Variantes de la primera ronda (se conservan para poder comparar)."""
    R = lado / 2
    cx = cy = R

    if numero == 1:
        # Caras: disco verde + arcos detras + cara en circulo centrado
        im = disco(lado)
        d = ImageDraw.Draw(im)
        arcos_spotify(d, cx, cy, R, R * 0.115, NEGRO, escala=0.94)
        f = cara_circular(cara, int(lado * 0.62), zoom=1.02)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        return im

    if numero == 2:
        # Como la 1 pero con anillo claro separando la cara del verde
        im = disco(lado)
        d = ImageDraw.Draw(im)
        arcos_spotify(d, cx, cy, R, R * 0.115, NEGRO, escala=0.94)
        diam = int(lado * 0.64)
        d.ellipse([(lado - diam) / 2 - lado * 0.012, (lado - diam) / 2 - lado * 0.012,
                   (lado + diam) / 2 + lado * 0.012, (lado + diam) / 2 + lado * 0.012],
                  fill=BLANCO)
        f = cara_circular(cara, int(lado * 0.62), zoom=1.02)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        return im

    if numero == 3:
        # La cara LLENA el disco: los arcos van encima, en blanco, abajo
        im = disco(lado, VERDE_OSCURO)
        f = cara_circular(cara, int(lado * 0.88), zoom=1.0)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        d = ImageDraw.Draw(im)
        arcos_spotify(d, cx, cy + R * 0.52, R, R * 0.075, BLANCO, escala=0.86)
        return im

    if numero == 4:
        # Cara llenando el disco + anillo verde grueso alrededor
        im = Image.new("RGBA", (lado * SS, lado * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([0, 0, lado * SS - 1, lado * SS - 1], fill=VERDE)
        d.ellipse([lado * SS * 0.055, lado * SS * 0.055,
                   lado * SS * 0.945, lado * SS * 0.945], fill=(0, 0, 0, 0))
        im = im.resize((lado, lado), Image.LANCZOS)
        f = cara_circular(cara, int(lado * 0.87), zoom=1.0)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        d2 = ImageDraw.Draw(im)
        arcos_spotify(d2, cx, cy + R * 0.50, R, R * 0.075, BLANCO, escala=0.84)
        return im

    if numero == 5:
        # Como la 1 pero el disco algo mas oscuro y arcos mas finos
        im = disco(lado, (24, 160, 72))
        d = ImageDraw.Draw(im)
        arcos_spotify(d, cx, cy, R, R * 0.095, NEGRO, escala=0.98)
        f = cara_circular(cara, int(lado * 0.60), zoom=1.04, desplazar_y=-0.01)
        im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
        return im

    # numero == 6: cuadrado redondeado en vez de circulo
    im = Image.new("RGBA", (lado * SS, lado * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, lado * SS - 1, lado * SS - 1], radius=lado * SS * 0.22,
                        fill=VERDE)
    im = im.resize((lado, lado), Image.LANCZOS)
    f = cara_circular(cara, int(lado * 0.66), zoom=1.02)
    im.alpha_composite(f, ((lado - f.width) // 2, (lado - f.height) // 2))
    d2 = ImageDraw.Draw(im)
    arcos_spotify(d2, cx, cy + R * 0.62, R, R * 0.075, NEGRO, escala=0.78)
    return im


def tira_pequena(variantes: list[Image.Image], lado: int) -> Image.Image:
    """Pone las variantes a tamaño de favicon, para ver cual aguanta."""
    alturas = [16, 24, 32, 48, 64]
    ancho = sum(lado + 10 for _ in variantes)
    alto = sum(a + 10 for a in alturas)
    tira = Image.new("RGB", (ancho, alto), (235, 235, 238))
    y = 5
    for a in alturas:
        x = 5
        for v in variantes:
            r = v.resize((a, a), Image.LANCZOS)
            tira.paste(r, (x + (lado - a) // 2, y), r)
            x += lado + 10
        y += a + 10
    return tira


def main() -> int:
    caras = {"A_cap": BASE / "cara1_cap_recorte.png", "B_pelo": BASE / "cara2_pelo_recorte.png"}
    faltan = [n for n, p in caras.items() if not p.exists()]
    if faltan:
        print(f"  [X] faltan recortes: {faltan}. Ejecuta antes scripts/recortar_caras.py")
        return 1

    numeros = [19, 20, 21, 22, 23, 24]
    lado = 320
    margen = 14
    ancho = len(numeros) * lado + (len(numeros) + 1) * margen
    alto_tira = 16 + 24 + 32 + 48 + 64 + 50
    hoja = Image.new("RGB", (ancho, 2 * (lado + alto_tira + 24) + margen),
                     (235, 235, 238))

    y = margen
    for nombre, ruta in caras.items():
        hechas = []
        for i, numero in enumerate(numeros):
            v = variante_final(numero, ruta, lado)
            hechas.append(v)
            hoja.paste(v, (margen + i * (lado + margen), y), v)
        y += lado + 10
        hoja.paste(tira_pequena(hechas, lado), (margen, y))
        y += alto_tira + 24
        print(f"  {nombre}: variantes {numeros} a {lado}px y a tamaño de favicon")

    hoja.save(BASE / "variantes4.png")
    print(f"\n  -> {BASE / 'variantes3.png'}")
    print(f"  variantes: {numeros}")
    print("  cada bloque: la fila grande, y debajo las mismas a 16/24/32/48/64 px")
    print("  (primer bloque: cara de la gorra · segundo: cara del pelo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
