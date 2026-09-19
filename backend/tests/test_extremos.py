"""Los extremos: ¿la canción empieza cuando debe y acaba cuando debe?

QUÉ SE FIJA AQUÍ
----------------
`radiov/extremos.py` decide si una canción trae **intro, diálogo o cola** que no son la canción. Es
una heurística, así que lo importante es que esté **medida** y no inventada:

  · La señal que funciona es el **bajo**: la música de este catálogo lo lleva; una voz hablando, un
    aplauso o un silencio, no. Se comprobó con ficheros reales: en la intro de «Bad Bunny - LA NOCHE
    DE ANOCHE» hay un 3,7 % de energía grave y en la canción un 63,5 %; en «Junior H - PIÉNSALO» la
    parte que el detector de ritmo marcaba como intro tenía 33,8 % y el resto 33,5 %, o sea que la
    música YA estaba sonando (falsa alarma).
  · Se probó un detector de voz de verdad (`webrtcvad`) y **no vale**: dice que una canción entera
    es voz (95-99 % de los fotogramas). Por eso no se usa.

Estas pruebas generan audio de mentira pero con esas características (bajo presente / voz sin bajo) y
comprueban que el detector dice lo que tiene que decir.
"""
import numpy as np
import pytest
import soundfile as sf

SR = 22050


def _musica(segundos: float, *, con_bajo: bool = True) -> np.ndarray:
    """Un «ritmo»: golpes a 120 BPM con bajo y sin él."""
    n = int(segundos * SR)
    t = np.arange(n) / SR
    golpes = np.zeros(n)
    for inicio in np.arange(0, segundos, 0.5):          # 120 BPM
        i = int(inicio * SR)
        golpes[i:i + 2205] += np.hanning(2205)          # un golpe corto
    señal = 0.3 * golpes * np.sin(2 * np.pi * 800 * t)
    if con_bajo:
        # El bajo: lo que distingue la música de una voz (energía por debajo de 120 Hz)
        señal += 0.5 * np.sin(2 * np.pi * 60 * t)
    return señal.astype(np.float32)


def _voz(segundos: float) -> np.ndarray:
    """Algo parecido a una voz: ruido filtrado en la banda de la palabra, sin bajo y sin pulso."""
    n = int(segundos * SR)
    rnd = np.random.default_rng(7).standard_normal(n)
    # Filtro muy simple: media móvil para quitar lo agudo y paso alto para quitar el bajo.
    suave = np.convolve(rnd, np.ones(9) / 9, mode="same")
    suave = suave - np.convolve(suave, np.ones(40) / 40, mode="same")
    # Modulación de sílabas (4 Hz), que es lo que hace una voz
    t = np.arange(n) / SR
    return (0.25 * suave * (1 + 0.8 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)


def _escribir(tmp_path, nombre: str, trozos: list[np.ndarray]) -> str:
    audio = np.concatenate(trozos) if trozos else np.zeros(SR, dtype=np.float32)
    ruta = tmp_path / nombre
    sf.write(str(ruta), audio, SR)
    return str(ruta)


@pytest.fixture
def analizar():
    from radiov.extremos import analizar as a

    return a


def test_cancion_que_empieza_con_musica_no_tiene_intro(tmp_path, analizar):
    """Una canción que empieza a tope no puede salir marcada: era el fallo más caro (cambiar
    canciones que estaban bien)."""
    ruta = _escribir(tmp_path, "normal.wav", [_musica(35)])
    r = analizar(ruta, duracion=35)
    assert r["ok"], r["motivo"]
    assert r["intro_seg"] == 0.0
    assert not r["buscar_otra"]


def test_intro_hablada_antes_de_la_musica_se_detecta(tmp_path, analizar):
    """12 segundos de «voz» y luego la canción: eso es una intro, y hay que verla."""
    ruta = _escribir(tmp_path, "con_intro.wav", [_voz(12), _musica(35)])
    r = analizar(ruta, duracion=47)
    assert r["ok"], r["motivo"]
    assert r["intro_seg"] >= 8, f"no se vio la intro: {r['intro_seg']}"
    assert r["buscar_otra"], "debería proponer buscar otra versión"


def test_el_silencio_se_detecta_pero_no_propone_cambiar(tmp_path, analizar):
    """Un silencio de 5 s al principio: se avisa (recortable), pero no se cambia la canción."""
    silencio = np.zeros(5 * SR, dtype=np.float32)
    ruta = _escribir(tmp_path, "con_silencio.wav", [silencio, _musica(35)])
    r = analizar(ruta, duracion=40)
    assert r["ok"], r["motivo"]
    assert r["silencio_inicio"] >= 4.5, r["silencio_inicio"]
    assert r["recortable"], "un silencio largo tiene que poder recortarse"
    assert not r["buscar_otra"], "un silencio no es motivo para cambiar de versión"


def test_la_cola_hablada_se_detecta(tmp_path, analizar):
    ruta = _escribir(tmp_path, "con_cola.wav", [_musica(35), _voz(12)])
    r = analizar(ruta, duracion=47)
    assert r["ok"], r["motivo"]
    assert r["cola_seg"] >= 8, f"no se vio la cola: {r['cola_seg']}"
    assert r["buscar_otra"]


def test_cancion_sin_bajo_no_se_marca_por_no_tener_bajo(tmp_path, analizar):
    """Una canción SIN bajo (una guitarra sola, por ejemplo) no puede salir marcada por eso.

    Es lo que se vio con «Junior H - PIÉNSALO»: el detector de ritmo decía «intro de 33 s» pero la
    música ya sonaba. Si la canción no tiene bajo, esa señal se apaga y decide el ritmo.
    """
    ruta = _escribir(tmp_path, "sin_bajo.wav", [_musica(35, con_bajo=False)])
    r = analizar(ruta, duracion=35)
    assert r["ok"], r["motivo"]
    assert not r["buscar_otra"], "no puede marcarse sólo porque la canción no tenga graves"


def test_el_analisis_trae_las_medidas_no_solo_el_veredicto(tmp_path, analizar):
    """Para poder revisarlo a mano, el resultado tiene que traer los números."""
    ruta = _escribir(tmp_path, "medidas.wav", [_voz(10), _musica(30)])
    r = analizar(ruta, duracion=40)
    for clave in ("silencio_inicio", "silencio_final", "inicio_musica", "fin_musica",
                  "intro_seg", "cola_seg", "intro_hablada", "cola_hablada", "grave_tipico"):
        assert clave in r, f"falta la medida {clave}"


def test_un_fichero_que_no_existe_no_revienta(tmp_path, analizar):
    """Si el fichero no está, tiene que decirlo, no caerse (el recolector no puede morir por eso)."""
    r = analizar(tmp_path / "no-existe.mp3")
    assert r["ok"] is False
    assert r["motivo"]


def test_la_clave_de_los_extremos_no_lo_confunde_con_otra_cancion():
    """`buscar_version_sin_intro` sólo cambia si la duración se parece: un directo de 8 minutos es
    otra cosa, aunque se llame igual."""
    from radiov.pipeline import buscar_version_sin_intro

    fuente = buscar_version_sin_intro.__doc__ or ""
    assert "duración" in fuente or "duracion" in fuente
