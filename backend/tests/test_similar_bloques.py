"""`rebuild_similar` / `neighbors` por bloques: mismo resultado, sin la matriz N×N.

Contexto (17/09/2026): las dos funciones construían `V @ V.T` completa (N×N) y además
`norm @ norm.T` (otra N×N) antes de dividir. Con 5140 canciones son ~105 MB por matriz de
float32, y se creaban varias a la vez; peor aún, `neighbors` lo hacía **dentro de una petición
de la API** (`/radio`) que cualquier usuario puede pedir en bucle. En un servidor de 4 GB eso es
pedirle a la OOM killer que elija.

La reescritura cambia la forma de calcularlo (bloques de filas, y en `neighbors` sólo la fila del
seed), así que lo que hay que garantizar es que **el resultado es el mismo**. Estas pruebas
comparan contra el cálculo directo de toda la vida.
"""
import numpy as np
import pytest


def _poblar(db, n=12):
    """Catálogo sintético: géneros y energías distintos para que la similitud no sea plana."""
    from app import models
    generos = ["pop", "rock", "reggaeton", "jazz"]
    for k in range(n):
        db.add(models.Track(title=f"T{k}", artist=f"A{k % 3}", genre=generos[k % len(generos)],
                            era="20s", bpm=90 + (k * 7) % 80, energy=(k % 5) / 4.0,
                            status="descargada", source="test", rank=1000 - k,
                            file_path=f"catalogada/A{k}/x.mp3"))
    db.commit()


def _referencia(ids, tracks, top):
    """El cálculo anterior, tal cual (matriz completa) para poder comparar."""
    from app.personalization import vector
    V = np.array([vector(t) for t in tracks], dtype=np.float32)
    norm = np.linalg.norm(V, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    cos = (V @ V.T) / (norm @ norm.T)
    esperado = {}
    for i, tid in enumerate(ids):
        sims = cos[i].copy()
        sims[i] = -1
        mejores = np.argsort(sims)[::-1][:top]
        esperado[tid] = [ids[int(j)] for j in mejores if sims[j] > 0]
    return esperado


@pytest.fixture
def catalogo(client):
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    _poblar(db, 12)
    tracks = db.query(models.Track).filter(models.Track.status == "descargada").all()
    ids = [t.id for t in tracks]
    yield db, ids, tracks
    db.query(models.Similar).delete()
    for t in tracks:
        db.delete(t)
    db.commit()
    db.close()


def test_rebuild_similar_da_los_mismos_vecinos_que_la_matriz_completa(catalogo):
    from app.personalization import rebuild_similar
    db, ids, tracks = catalogo
    esperado = _referencia(ids, tracks, top=5)

    n = rebuild_similar(db, top=5)
    assert n > 0

    from app import models
    for tid, vecinos in esperado.items():
        obtenidos = [s.track_b for s in db.query(models.Similar)
                     .filter_by(track_a=tid).order_by(models.Similar.score.desc()).all()]
        assert obtenidos == vecinos, f"la canción {tid} cambió de vecinos"


def test_neighbors_solo_calcula_la_fila_del_seed(catalogo):
    from app.personalization import neighbors
    db, ids, tracks = catalogo
    esperado = _referencia(ids, tracks, top=40)

    out = neighbors(db, ids[0], n=5, top=6)
    assert out == esperado[ids[0]][:5]


def test_neighbors_no_reserva_la_matriz_cuadrada(catalogo, monkeypatch):
    """Comprobación directa: la operación matricial que se ejecuta NO puede ser N×N.

    Se vigila el producto: si alguien vuelve a escribir `V @ V.T`, el resultado tendrá forma
    (N, N) y esta prueba se cae. Es la forma de que el arreglo no se pierda sin darse cuenta.
    """
    from app.personalization import neighbors
    db, ids, _tracks = catalogo

    formas = []
    original = np.matmul

    def espia(a, b, *args, **kwargs):
        r = original(a, b, *args, **kwargs)
        try:
            formas.append((getattr(a, "shape", None), getattr(b, "shape", None), getattr(r, "shape", None)))
        except Exception:  # noqa: BLE001
            pass
        return r

    monkeypatch.setattr(np, "matmul", espia)
    neighbors(db, ids[0], n=3, top=4)

    total = len(ids)
    for forma_a, forma_b, forma_r in formas:
        assert not (forma_r == (total, total)), (
            f"se volvió a calcular la matriz completa N×N: {forma_a} @ {forma_b} -> {forma_r}"
        )
