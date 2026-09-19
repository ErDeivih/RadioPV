import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from radiov.quality import _PORTUGUES_RE, parece_portugues

casos = [
    ("Tout en Gucci", "Ninho"),
    ("Balek (feat. Aya Nakamura, MC YOSHI, Mauvais Djo & Kokosvoice)", "TRIANGLE DES BERMUDES"),
    ("Here I Am / Small Axe (Come And Take Me)", "UB40"),
    ("Lettre à une femme", "Ninho"),
    ("Aicha", "Khaled"),
    ("Só um Pouquinho", "X"),
]
for t, a in casos:
    m = _PORTUGUES_RE.search(f"{t} {a}")
    print(f"{'SI ' if m else 'no '} {a} - {t}"[:70], "->", repr(m.group(0)) if m else "")
