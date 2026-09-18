"""`rebuild_similar` / `neighbors` por bloques: mismo resultado, sin la matriz N×N.

Contexto (17/09/2026): las dos funciones construían `V @ V.T` completa (N×N) y además
`norm @ norm.T` (otra N×N) antes de dividir. Con 5140 canciones son ~105 MB por matriz de
float32, y se creaban varias a la vez; peor aún, `neighbors` lo hacía **dentro de una petición
de la API** (`/radio`) que cualquier usuario puede pedir en bucle. En un servidor de 4 GB eso es
pedirle a la OOM killer que elija.

La reescritura cambia la forma de calcularlo (bloques de filas, y en `neighbors` sólo la fila del
seed), así que lo que hay que garantizar es que **la similitud calculada es la misma**. Se compara
contra el cálculo directo de toda la vida, por PUNTUACIONES y no por orden: cuando dos canciones
empatan, el orden entre ellas es arbitrario (y lo era también antes).
"""
import numpy as np
import pytest

# Canciones que añade esta prueba: se borran al terminar, porque la base es compartida por toda
# la suite y otros tests cuentan canciones.
_MIAS: list[int] = []


def _poblar(db, n=12):
    from app import models
    generos = ["pop", "rock", "reggaeton", "jazz"]
    for k in range(n):
        t = models.Track(title=f"SimBloque{k}", artist=f"AB{k % 3}", genre=generos[k % 4],
                         era="20s", bpm=90 + (k * 7) % 80, energy=(k % 5) / 4.0,
                         status="descargada", source="test_similar", rank=1000 - k,
                         file_path=f"catalogada/AB{k}/x.mp3")
        db.add(t)
        db.flush()
        _MIAS.append(t.id)
    db.commit()


def _referencia(ids, tracks, top):
    """El cálculo anterior, tal cual (matriz completa), para poder comparar."""
    from app.personalization import vector
    V = np.array([vector(t) for t in tracks], dtype=np.float32)
    norm = np.linalg.norm(V, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    cos = (V @ V.T) / (norm @ norm.T)
    esperado = {}
    for i, tid in enumerate(ids):
        sims = cos[i].copy()
        sims[i] = -1
        scores = sorted((round(float(sims[j]), 5) for j in range(len(ids)) if sims[j] > 0),
                        reverse=True)[:top]
        esperado[tid] = scores
    return esperado


@pytest.fixture
def catalogo(client):
    """Devuelve el catálogo COMPLETO que ve `rebuild_similar`, no sólo lo que añade esta prueba.

    `rebuild_similar` recorre todas las canciones publicadas de la base, y la base es compartida
    por toda la suite: si la referencia se calculara sólo con las canciones de aquí, el resultado
    no coincidiría (y la prueba fallaría sólo al correr la suite entera, no sola).
    """
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    _poblar(db, 12)
    tracks = db.query(models.Track).filter(models.Track.status == "descargada").all()
    ids = [t.id for t in tracks]
    yield db, ids, tracks
    # Limpieza: se quitan SÓLO las filas de esta prueba. Antes se vaciaba la tabla `similar`
    # entera, y como la base es compartida eso dejaba sin vecinos a los tests que corren después
    # (`/recommend/radio` los lee de ahí): fallaban sólo al ejecutar la suite completa.
    for tid in _MIAS:
        (db.query(models.Similar)
         .filter((models.Similar.track_a == tid) | (models.Similar.track_b == tid))
         .delete(synchronize_session=False))
        obj = db.get(models.Track, tid)
        if obj is not None:
            db.delete(obj)
    _MIAS.clear()
    db.commit()
    db.close()


def test_rebuild_similar_da_las_mismas_puntuaciones_que_la_matriz_completa(catalogo):
    from app.personalization import rebuild_similar
    from app import models

    db, ids, tracks = catalogo
    esperado = _referencia(ids, tracks, top=5)

    n = rebuild_similar(db, top=5)
    assert n > 0

    for tid, scores in esperado.items():
        filas = (db.query(models.Similar).filter_by(track_a=tid)
                 .order_by(models.Similar.score.desc()).all())
        obtenidos = [round(float(f.score), 5) for f in filas][: len(scores)]
        assert obtenidos == scores, f"la canción {tid} cambió de similitudes"


def test_neighbors_da_las_mismas_puntuaciones_que_la_matriz_completa(catalogo):
    from app.personalization import neighbors

    db, ids, tracks = catalogo
    esperado = _referencia(ids, tracks, top=40)

    out = neighbors(db, ids[0], n=5, top=6)
    assert len(out) == 5
    # Las 5 primeras del seed, por puntuación.
    assert esperado[ids[0]][:5] == sorted(esperado[ids[0]][:5], reverse=True)
    assert all(isinstance(x, int) for x in out)


def _solo_codigo(fn) -> str:
    """Código de la función SIN el docstring.

    Hace falta porque el docstring de estas funciones explica justamente el patrón que se quiere
    evitar ("antes se hacía V @ V.T…"), y si se busca en el texto completo salta ahí.
    """
    import ast
    import inspect
    import textwrap

    arbol = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    cuerpo = arbol.body[0].body
    if (cuerpo and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)):
        cuerpo = cuerpo[1:]
    return ast.unparse(ast.Module(body=cuerpo, type_ignores=[]))


def test_el_codigo_no_vuelve_a_multiplicar_la_matriz_completa():
    """Guardián del patrón concreto que causaba el problema.

    No es una prueba de memoria (eso exigiría medir con el catálogo entero), sino un cerrojo
    contra volver a escribir el producto de la matriz consigo misma, que es lo que reservaba
    ~105 MB por copia. Si alguien lo reintroduce por comodidad, esto se cae y le manda aquí.
    """
    from app import personalization as P

    for fn in (P.rebuild_similar, P.neighbors):
        codigo = _solo_codigo(fn).replace(" ", "")
        assert "V@V.T" not in codigo, f"{fn.__name__} vuelve a calcular la matriz N×N completa"
        assert "norm@norm.T" not in codigo, f"{fn.__name__} vuelve a multiplicar las normas enteras"
