"""El envío al servidor: en tandas, con tope de tiempo, y sin dar por enviado lo que no llegó.

EL FALLO QUE FIJA ESTA PRUEBA (20/09/2026)
------------------------------------------
Se mandaron 544 MB de una vez (diez canciones, entre ellas mezclas de tres horas) y el envío por
`ssh … docker run alpine tar -xf -` se quedó **colgado a mitad**: 14 minutos sin moverse. El tope del
envío estaba en una hora, así que la vuelta entera quedó parada, y como la tarea programada de
Windows es `IgnoreNew`, la vuelta siguiente no llegó a arrancar: **el PC dejó de descargar y de
publicar sin avisar**. Y peor: si el audio no llegaba, las fichas ya estaban en el servidor, así que
la canción aparecía en la aplicación y no sonaba.

Lo que se comprueba aquí:
  · la lista se parte en tandas de ~120 MB (una tanda enorme es lo que se atasca);
  · una tanda que se pasa de tiempo se corta y las demás siguen;
  · una tanda que falla no devuelve sus ficheros como enviados (se reintentan).
"""
import sys
from pathlib import Path


def _recolector():
    raiz = Path(__file__).resolve().parents[2]
    if str(raiz / "pc") not in sys.path:
        sys.path.insert(0, str(raiz / "pc"))
    import recolector_pc
    return recolector_pc


def _falso(tmp_path, nombre: str, mb: float) -> Path:
    """Un fichero de mentira del tamaño pedido (no se escribe nada: se reserva el hueco)."""
    p = tmp_path / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.truncate(int(mb * 1024 * 1024))
    return p


def test_se_parte_en_tandas_de_120_mb(tmp_path):
    rcp = _recolector()
    ficheros = [(_falso(tmp_path, f"f{i}.mp3", 50), f"catalogada/f{i}.mp3") for i in range(6)]
    tandas = rcp._en_tandas(ficheros)
    assert len(tandas) == 3, [len(t) for t in tandas]        # 50+50, 50+50, 50+50
    assert sum(len(t) for t in tandas) == 6


def test_un_fichero_mas_grande_que_la_tanda_va_solo(tmp_path):
    """Una sesión de tres horas no se puede quedar sin enviar por pasarse del tope."""
    rcp = _recolector()
    grande = (_falso(tmp_path, "sesion.mp3", 300), "catalogada/sesion.mp3")
    pequeno = (_falso(tmp_path, "tema.mp3", 5), "catalogada/tema.mp3")
    tandas = rcp._en_tandas([grande, pequeno])
    assert tandas == [[grande], [pequeno]]


def test_una_tanda_colgada_se_corta_y_no_tumba_el_envio(tmp_path, monkeypatch):
    """Un envío que se atasca tiene que cortarse: si no, la vuelta entera se queda parada."""
    rcp = _recolector()
    ficheros = [(_falso(tmp_path, "a.mp3", 50), "catalogada/a.mp3"),
                (_falso(tmp_path, "b.mp3", 50), "catalogada/b.mp3"),
                (_falso(tmp_path, "c.mp3", 50), "catalogada/c.mp3")]
    llamadas = []

    class Resultado:
        returncode = 0
        stderr = ""

    def falso_run(cmd, **kw):
        llamadas.append(cmd)
        # La PRIMERA tanda se cuelga en sus dos intentos (como el envío de 544 MB de verdad); las
        # siguientes van bien.
        if len(llamadas) <= 2:
            raise rcp.subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))
        return Resultado()

    monkeypatch.setattr(rcp.subprocess, "run", falso_run)
    cfg = {"datos_locales": str(tmp_path), "servidor": "david@servidor.local"}
    llegaron = rcp._enviar_ficheros(cfg, ficheros, "/srv/data/media/music", "música")

    # La primera tanda se colgó (2 intentos) y no cuenta; la segunda llegó.
    assert "catalogada/a.mp3" not in llegaron
    assert "catalogada/c.mp3" in llegaron
    assert len(llamadas) == 3


def test_sin_ficheros_no_hace_nada(tmp_path):
    rcp = _recolector()
    cfg = {"datos_locales": str(tmp_path), "servidor": "x"}
    assert rcp._enviar_ficheros(cfg, [], "/destino", "música") == []
    assert rcp._enviar_ficheros(cfg, [(tmp_path / "no-existe.mp3", "x")], "/destino", "música") == []


def test_el_presupuesto_de_una_vuelta_corta_el_envio(tmp_path, monkeypatch):
    """Un atraso grande no puede hacer que la vuelta se pase de la hora que le da Windows.

    El 21/09/2026 había 172 canciones esperando su audio (más de 2 GB): el envío encadenaba tandas sin
    parar y la vuelta se acercaba al límite de una hora de la tarea programada. Si la mata a mitad se
    pierde el resto de la vuelta, así que ahora la fase de publicación tiene su propio presupuesto y lo
    que falte se manda en la siguiente (no se apunta como enviado, así que se reintenta solo).
    """
    rcp = _recolector()
    ficheros = [(_falso(tmp_path, f"f{i}.mp3", 10), f"catalogada/f{i}.mp3") for i in range(4)]
    llamadas = []

    class Resultado:
        returncode = 0
        stderr = ""

    def falso_run(cmd, **kw):
        llamadas.append(cmd)
        return Resultado()

    monkeypatch.setattr(rcp.subprocess, "run", falso_run)
    # El reloj avanza: tras la primera tanda el presupuesto ya está agotado.
    reloj = {"t": 0.0}

    def reloj_falso():
        reloj["t"] += 10 ** 6
        return reloj["t"]

    monkeypatch.setattr(rcp.time, "time", reloj_falso)
    cfg = {"datos_locales": str(tmp_path), "servidor": "david@servidor.local"}
    llegaron = rcp._enviar_ficheros(cfg, ficheros, "/srv/data/media/music", "música")

    assert len(llamadas) < len(ficheros), f"se enviaron todas las tandas: {len(llamadas)}"
    assert len(llegaron) < len(ficheros), "lo que no se envió no puede darse por enviado"


def test_el_tope_de_tiempo_es_razonable():
    """20 minutos para 120 MB: si tarda más, está colgado (14 minutos fue el atasco real)."""
    rcp = _recolector()
    assert 300 <= rcp.TIEMPO_MAX_ENVIO <= 3600
    assert 300 <= rcp.TIEMPO_MAX_PUBLICAR <= 3600
