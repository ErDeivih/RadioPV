"""C2 · con_cuota_decadas reserva 1 de cada 4 para pre-2000."""
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
from radiov.catalog import con_cuota_decadas  # noqa: E402


def test_cuota_decadas():
    # 8 temas de 2024 + 4 de los 80s (mezcla). La cuota (1/4) debe intercalar los viejos.
    cands = [{"year": 2024, "title": f"n{i}"} for i in range(8)] + \
            [{"year": 1985, "title": f"v{i}"} for i in range(4)]
    out = con_cuota_decadas(cands)
    viejos = [c for c in out if c["year"] < 2000]
    # con 1-de-4 sobre 12 items, ~3 viejos salen (ni 0 ni los 4)
    assert 2 <= len(viejos) <= 4, f"viejos: {len(viejos)}"
    # todos los viejos siguen en la lista (no se pierden) y empiezan de forma espaciada
    assert len(viejos) == 4, "no deben perderse viejos"
