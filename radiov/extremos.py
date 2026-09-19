"""Mira los EXTREMOS de una canción: lo que hay antes de que empiece y después de que acabe.

POR QUÉ EXISTE
--------------
Los vídeos de YouTube (sobre todo los «oficiales») suelen traer cosas que **no son la canción**:

  · una **intro hablada** o un diálogo («¡Muy buenas a todos!», una escena de película, un anuncio);
  · unos segundos de **silencio** al principio;
  · una **cola** al final: el presentador despidiéndose, el «dale like y suscríbete», otro silencio…

En la aplicación eso se nota muchísimo: pones la canción y los primeros 20 segundos son alguien
hablando. El usuario lo pidió así: *«revisa si algunas tienen, al estar descargado de YouTube, inicio,
final, diálogos, cosas que no pertenezcan a la letra de la canción, para buscar otra versión que no lo
tenga»*.

CÓMO SE MIRA (y qué se puede y qué no)
--------------------------------------
No hay forma de «escuchar» y entender palabras sin un modelo de voz, así que esto **no** transcribe
nada. Lo que hace es mirar el SONIDO, que es suficiente para lo que se busca:

  1. **Silencio**: se mide la energía por tramos y se ven los tramos de delante y de detrás que están
     por debajo del ruido de la propia canción. Eso es exacto.
  2. **¿Aquí hay música?**: la música tiene **pulso**. Se calcula, en ventanas de 4 segundos, cuánto
     se repite el patrón rítmico (autocorrelación de la envolvente de ataques, buscando un pulso de
     50-200 golpes por minuto). Una voz hablando sola no tiene ese pulso; una canción sí. Con eso se
     saca **en qué segundo empieza la música de verdad** y en cuál termina.

Lo que sale de aquí es una **medida**, no un veredicto: `inicio_musica` (segundo en el que ya hay
música seguida) y `fin_musica`. A partir de ahí, `hay_intro`/`hay_cola` con los márgenes de abajo. Es
una heurística: acierta en los casos claros (intro hablada, silencio, despedida) y puede fallar en
canciones que empiezan a capela o con un instrumento suave. Por eso **no se borra nada por esto**:
sirve para buscar una versión mejor y, si no la hay, para dejarlo apuntado y poder revisarlo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# Márgenes: a partir de aquí se considera que hay algo que no es la canción.
MIN_INTRO = 6.0        # segundos de «no música» al principio para avisar
MIN_COLA = 6.0         # ídem al final
MIN_SILENCIO = 3.0     # silencio (sin sonido) al principio o al final que ya molesta
# Voz/diálogo: más exigente que el aviso, porque lo que dispara es CAMBIAR la canción por otra
# versión. Comprobado con ficheros reales: hay canciones que empiezan con un instrumento suave o un
# «build-up» de 6 segundos en el que el detector no encuentra pulso, y eso NO es una intro hablada.
# Con 8 segundos sólo salta cuando hay una intro de verdad (las que se han visto: 9 s, 18 s, 30 s).
MIN_VOZ = 8.0
VENTANA = 4.0          # tamaño de la ventana donde se busca el pulso
SALTO = 1.0            # cada cuánto se avanza
SEGUIDO = 20.0         # cuántos segundos seguidos de música hacen falta para decir «aquí empieza»


def _cargar(ruta: str | Path, *, offset: float = 0.0, duration: float = 60.0):
    import librosa

    return librosa.load(str(ruta), sr=22050, mono=True, offset=max(0.0, offset),
                        duration=duration)


def _energia_db(y) -> "object":
    import librosa
    import numpy as np

    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    return librosa.amplitude_to_db(np.maximum(rms, 1e-10), ref=1.0)


def _banda_grave(y, sr: int) -> "object":
    """Proporción de energía por debajo de 120 Hz, fotograma a fotograma.

    POR QUÉ ESTA MEDIDA Y NO «¿SUENA A VOZ?»
    ----------------------------------------
    Se probó un detector de voz de verdad (`webrtcvad`) y **no sirve aquí**: dice que una canción
    entera es voz (el 95-99 % de los fotogramas), porque está hecho para llamadas de teléfono. Lo que
    sí distingue, y se comprobó con ficheros reales:

      · En la intro hablada de «Bad Bunny - LA NOCHE DE ANOCHE» hay un **3,7 %** de energía grave, y
        en la canción un **63,5 %**: esa intro NO es la canción.
      · En «Junior H - PIÉNSALO», el detector de pulso decía «intro de 33 s», pero esa parte tiene
        **33,8 %** de graves y el resto **33,5 %**: la música ya está sonando. Era una falsa alarma.

    O sea: la música de este catálogo lleva bajo; una intro hablada, un diálogo, un aplauso o un
    silencio, no. Comparando la parte de delante con el cuerpo de la canción se ve claro.
    """
    import librosa
    import numpy as np

    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    graves = S[freqs < 120].sum(axis=0)
    total = S.sum(axis=0) + 1e-9
    return graves / total


def _es_musica_por_segundo(y, sr: int, *, umbral_pulso: float = 0.18) -> "object":
    """Devuelve un booleano por segundo: ¿aquí ya está sonando la canción?

    DECIDE EL BAJO, Y SÓLO EL BAJO
    ------------------------------
    Se probaron dos señales y **una se descartó**, con números:

      · **El ritmo** (envolvente de ataques y su autocorrelación): se midió con audio sintético
        controlado y sale al revés de lo que hace falta — una música con golpes a 120 BPM daba 0,18 de
        «pulso» y una voz sintética modulada como el habla daba 0,79. Es decir: la voz puntuaba MÁS
        que la música. Como señal para decir «aquí hay canción» no sirve, y en el catálogo real fue la
        causa de marcar canciones que estaban bien (Junior H - PIÉNSALO).
      · **El bajo** (energía por debajo de 120 Hz comparada con el cuerpo de la canción): funciona.
        Comprobado con ficheros reales: la intro de «Bad Bunny - LA NOCHE DE ANOCHE» tiene 3,7 % de
        graves y su canción 63,5 %; «PIÉNSALO» tiene 33,8 % en la parte «sospechosa» y 33,5 % en el
        resto, o sea que ahí ya sonaba la música.

    Y si la canción **no tiene bajo** (una guitarra sola, algo acústico), no se acusa a nadie: sin una
    señal fiable en la que apoyarse, lo honesto es no decir nada. Lo único que se seguirá viendo en
    esos casos es el silencio, que se mide de forma exacta.
    """
    import numpy as np

    graves = _banda_grave(y, sr)
    fps = sr / 512
    segundos = int(len(graves) / fps)

    # El «cuerpo» de la canción: a partir del segundo 20 (o de un tercio del trozo, si es corto), que
    # es donde con seguridad ya está la música.
    inicio_cuerpo = min(20, max(3, segundos // 3))
    cuerpo = graves[int(inicio_cuerpo * fps):]
    grave_tipico = float(np.median(cuerpo)) if len(cuerpo) else float(np.median(graves) if len(graves) else 0.0)
    hay_bajo = grave_tipico > 0.04

    if not hay_bajo:
        # Sin bajo no hay señal: se da por bueno todo (no se acusa) y el silencio se mira aparte.
        return np.ones(max(segundos, 1), dtype=bool), grave_tipico

    musica = []
    for seg in range(segundos):
        trozo = graves[int(seg * fps):int((seg + 1) * fps)]
        grave_seg = float(np.mean(trozo)) if len(trozo) else 0.0
        musica.append(bool(grave_seg >= 0.4 * grave_tipico))
    return np.array(musica, dtype=bool), grave_tipico


def _silencio_inicial(y, sr: int) -> float:
    """Segundos de silencio al principio (por debajo del ruido propio de la grabación)."""
    import numpy as np

    db = _energia_db(y)
    if len(db) < 4:
        return 0.0
    # Umbral: 30 dB por debajo de la mediana de la propia canción (que es como suena «nada» aquí),
    # y nunca por encima de -45 dBFS (si no, una canción muy bajita parecería silencio entera).
    umbral = min(float(np.median(db)) - 30.0, -45.0)
    seg = 0.0
    for valor in db:
        if valor < umbral:
            seg += 512 / sr
        else:
            break
    return seg


def _silencio_final(y, sr: int) -> float:
    import numpy as np

    db = _energia_db(y)
    if len(db) < 4:
        return 0.0
    umbral = min(float(np.median(db)) - 30.0, -45.0)
    seg = 0.0
    for valor in reversed(db):
        if valor < umbral:
            seg += 512 / sr
        else:
            break
    return seg


def analizar(ruta: str | Path, *, duracion: Optional[float] = None,
             umbral_pulso: float = 0.18) -> dict:
    """Analiza los extremos de un fichero. Devuelve medidas, no un veredicto.

    Claves del resultado:
      · `silencio_inicio` / `silencio_final` — segundos de silencio en cada punta.
      · `inicio_musica` — segundo en el que la música ya es seguida (None si no se pudo saber).
      · `fin_musica` — segundo (contado desde el principio del trozo final) en el que la música
        termina.
      · `hay_intro` / `hay_cola` — si lo anterior pasa de los márgenes (`MIN_INTRO`, `MIN_COLA`).
      · `intro_seg` / `cola_seg` — cuántos segundos hay que quitar para que empiece/termine la música.
    """
    import librosa
    import numpy as np

    ruta = Path(ruta)
    resultado = {
        "silencio_inicio": 0.0, "silencio_final": 0.0,
        "inicio_musica": None, "fin_musica": None,
        "hay_intro": False, "hay_cola": False,
        "intro_seg": 0.0, "cola_seg": 0.0,
        # `intro_hablada`/`cola_hablada` son los segundos de SONIDO que no es la canción (voz,
        # diálogo, ambiente). `buscar_otra` dice si por eso merece la pena buscar otra versión;
        # `recortable`, si lo que hay es silencio y basta con recortarlo.
        "intro_hablada": 0.0, "cola_hablada": 0.0,
        "buscar_otra": False, "recortable": False,
        # Cuánta energía grave tiene el cuerpo de la canción (0-1). Si es muy baja, la señal de
        # «¿hay bajo aquí?» no sirve y se decide sólo por el ritmo.
        "grave_tipico": 0.0,
        "ok": False, "motivo": "",
    }

    try:
        # --- principio: primeros 60 s ---
        y, sr = _cargar(ruta, offset=0.0, duration=60.0)
        if y is None or len(y) < sr:                      # menos de 1 s: no se puede analizar
            resultado["motivo"] = "audio demasiado corto"
            return resultado
        resultado["silencio_inicio"] = round(_silencio_inicial(y, sr), 1)
        musica, grave_tipico = _es_musica_por_segundo(y, sr, umbral_pulso=umbral_pulso)
        resultado["grave_tipico"] = round(float(grave_tipico), 3)
        if len(musica):
            # «Aquí ya empieza la canción» = el primer segundo desde el que hay música de forma
            # seguida: al menos el 80 % de los siguientes `SEGUIDO` segundos. No se pide el 100 %
            # porque un silencio de medio segundo en medio de una intro musical (o un respiro) no
            # significa que la música haya parado; se comprobó que exigirlo todo retrasaba el
            # «empieza aquí» decenas de segundos y marcaba canciones normales como si tuvieran intro.
            necesarios = max(1, int(SEGUIDO * 0.8))
            inicio = None
            for i in range(len(musica)):
                trozo = musica[i:i + necesarios]
                if len(trozo) >= necesarios and int(trozo.sum()) >= necesarios:
                    inicio = i
                    break
            if inicio is None and musica.any():
                inicio = int(len(musica) - 1 - musica[::-1].argmax())
            if inicio is not None:
                resultado["inicio_musica"] = round(float(inicio), 1)

        # --- final: últimos 40 s ---
        total = duracion
        if total is None:
            try:
                total = float(librosa.get_duration(path=str(ruta)))
            except Exception:  # noqa: BLE001
                total = None
        if total and total > 20:
            desde = max(0.0, total - 40.0)
            yf, srf = _cargar(ruta, offset=desde, duration=40.0)
            if yf is not None and len(yf) > srf:
                resultado["silencio_final"] = round(_silencio_final(yf, srf), 1)
                musica_f, _gt = _es_musica_por_segundo(yf, srf, umbral_pulso=umbral_pulso)
                if len(musica_f):
                    ultimo = None
                    for i in range(len(musica_f) - 1, -1, -1):
                        # La última música que además tenga música cerca: así un golpe suelto al
                        # final (una sintonía, un «toque») no cuenta como que sigue la canción.
                        if musica_f[i] and bool(musica_f[max(0, i - 2):i + 1].any()):
                            ultimo = i
                            break
                    if ultimo is not None:
                        resultado["fin_musica"] = round(float(desde + ultimo + 1), 1)

        # --- veredictos ---
        # Se separa lo que es SÓLO SILENCIO de lo que es SONIDO que no es la canción (voz, diálogo,
        # ambiente, un anuncio). No se arreglan igual: el silencio se recorta y ya está; para una
        # intro hablada lo que se busca es OTRA VERSIÓN de la canción, porque recortar a ojo es
        # arriesgado (a veces la voz se solapa con el principio de la música).
        intro_medida = resultado["inicio_musica"]
        if intro_medida is not None:
            resultado["intro_seg"] = round(float(intro_medida), 1)
            resultado["intro_hablada"] = round(
                max(0.0, float(intro_medida) - resultado["silencio_inicio"]), 1)
        if resultado["silencio_inicio"] > resultado["intro_seg"]:
            resultado["intro_seg"] = resultado["silencio_inicio"]
        resultado["hay_intro"] = (resultado["intro_seg"] > MIN_INTRO
                                  or resultado["silencio_inicio"] > MIN_SILENCIO)

        fin = resultado["fin_musica"]
        if fin is not None and total:
            resultado["cola_seg"] = round(max(0.0, float(total - fin)), 1)
            resultado["cola_hablada"] = round(
                max(0.0, resultado["cola_seg"] - resultado["silencio_final"]), 1)
        if resultado["silencio_final"] > resultado["cola_seg"]:
            resultado["cola_seg"] = resultado["silencio_final"]
        resultado["hay_cola"] = (resultado["cola_seg"] > MIN_COLA
                                 or resultado["silencio_final"] > MIN_SILENCIO)

        # ¿Merece la pena buscar otra versión? Sólo si hay VOZ o ambiente (no música) en los
        # extremos, y bastante: ver `MIN_VOZ`. Si lo que hay es silencio, lo que toca es recortar.
        resultado["buscar_otra"] = (resultado["intro_hablada"] >= MIN_VOZ
                                    or resultado["cola_hablada"] >= MIN_VOZ)
        # `recortable`: hay silencio de sobra en alguna punta (eso sí se puede quitar sin riesgo).
        resultado["recortable"] = (resultado["silencio_inicio"] > MIN_SILENCIO
                                   or resultado["silencio_final"] > MIN_SILENCIO)

        resultado["ok"] = True
        return resultado
    except Exception as e:  # noqa: BLE001
        resultado["motivo"] = f"{type(e).__name__}: {str(e)[:80]}"
        return resultado
