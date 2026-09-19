"""Comprobación a mano del clasificador y de los márgenes de duración.

Se ejecuta en el PC (no necesita el servidor): así se ve de un vistazo que una sesión de DJ
entra, que un mashup corto entra y que una compilación de 5 horas o un tono de móvil no.
"""
import sys

sys.path.insert(0, ".")

from radiov.quality import clasificar, revisar  # noqa: E402

CASOS = [
    ("Now You're Gone (feat. DJ Mental Theo's Bazzheadz)", "Basshunter", 130, "cancion normal"),
    ("SET DJ YURI PEDRADA - TRAVA CHIP", "dj yuri pedrada", 480, "sesion de DJ"),
    ("REGGAETON VIEJO / OLD SCHOOL VOL. 1 LOS MEJORES", "DJ RONALD HESS", 1320, "sesion de DJ"),
    ("Yo x Ti, Tu x Mi", "ROSALIA", 200, "titulo con x, no es mashup"),
    ("Daddy Yankee: Bzrp Music Sessions, Vol. 0/66", "Bizarrap", 120, "session en el titulo"),
    ("Ba Ba Bad Remix", "Kybba", 150, "remix"),
    ("Blinding Lights", "The Weeknd", 200, "cancion normal"),
    ("Trolls 2 Many Hits Mashup", "Anna Kendrick", 63, "mashup corto"),
    ("Party Mix Session 1.5", "AV8", 72, "mezcla corta"),
    ("Best Mashup Mix", "djpino", 1800, "mashup largo de DJ"),
    ("2024 Top Hits.wav", "2024 Hit Playlist", 17340, "compilacion de 5 h"),
    ("Promiscuous Girl (Remix)", "Ringtone Hits", 63, "tono de movil"),
    ("Teenage Mutant Ninja Turtles Cartoon Opening Theme", "TV Hits", 58, "sintonia"),
    ("EDM Workout Music 2020 Top 100 Hits (2hr DJ Mix)", "Workout Electronica", 6780, "gimnasio"),
    ("Cancion cualquiera", "Alguien", 40, "demasiado corta"),
]

print(f"{'tipo':9s} {'entra?':7s} {'motivo':44s} que es")
print("-" * 110)
for titulo, artista, dur, que_es in CASOS:
    tipo = clasificar(titulo, artista, dur)
    ok, motivo = revisar({"title": titulo, "artist": artista, "duration": dur})
    print(f"{str(tipo):9s} {'SI' if ok else 'NO':7s} {motivo[:44]:44s} {que_es}")
