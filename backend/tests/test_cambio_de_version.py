"""Cambiar una canción por «otra versión» sin intro: sólo cuando es SEGURO que es la misma.

FALLO REAL (20/09/2026)
-----------------------
La detección de intros funciona, pero al cambiar automáticamente se cambió **la sesión que el usuario
había pedido a mano**:

    pedida:    «Dj RuLoX - Mix REGGAETON VIEJO (Old School)»  (36 min, 67 MB, canal Dj RuLoX)
    puesta:    otra subida con un título casi igual, de otro canal («DJ Naydee»), de duración parecida

Son **mezclas distintas**: otro orden, otros cortes y otras canciones dentro. No es «la misma canción
sin la intro», es otro trabajo. Para una canción normal, cambiar el vídeo oficial por el audio del
disco es seguro (es la misma grabación); para una mezcla, no.

Estas pruebas fijan las dos protecciones que se añadieron:

  1. **Las mezclas no se cambian solas** (más de 20 minutos o clasificadas como sesión): sólo se
     informa y queda apuntado, para que el usuario decida.
  2. **La duración tiene que encajar con «la misma grabación sin el trozo de más»**: puede ser más
     corta, pero no más de lo que se quiere quitar (intro+cola) más 30 s, y no puede ser más larga que
     un 10 %. Antes se admitía un ±25 %, y por ahí cabía cualquier cosa con el mismo título.
"""
import inspect

from radiov.pipeline import buscar_version_sin_intro


def test_una_mezcla_no_se_cambia_sola():
    """El caso real: la sesión de 36 minutos que había pedido el usuario."""
    respuesta = buscar_version_sin_intro(
        "Dj RuLoX",
        "Mix REGGAETON VIEJO (Old School) // Daddy Yankee, Plan B, Don Omar, Calle 13, Y MÁS // Dj RuLoX",
        6005, "catalogada/Dj RuLoX/x.mp3",
        intro_actual=18, cola_actual=6, duracion=2174)
    assert respuesta.startswith("es una mezcla"), respuesta
    assert "no se cambia" in respuesta


def test_una_mezcla_larga_tampoco_aunque_no_diga_sesion():
    """Aunque el título no diga «sesión», si dura más de 20 minutos es una mezcla y no se toca."""
    respuesta = buscar_version_sin_intro(
        "Alguien", "MIX CUMBIAS VV1", 1, "catalogada/x.mp3",
        intro_actual=30, cola_actual=5, duracion=3600)
    assert respuesta.startswith("es una mezcla"), respuesta


def test_la_duracion_se_comprueba_por_dos_lados():
    """Se mira el código: la alternativa no puede ser mucho más corta ni más larga.

    No se llama a YouTube en una prueba (tardaría y no sería reproducible), así que se comprueba la
    regla escrita: es lo que hay que evitar que se cambie sin querer.
    """
    fuente = inspect.getsource(buscar_version_sin_intro)
    assert "margen_abajo" in fuente, "falta el margen de duración por abajo"
    assert "* 1.10" in fuente, "falta el tope de duración por arriba"
    # Y el comentario del margen antiguo (±25 %) ya no está
    assert "> 0.25" not in fuente, "sigue el margen antiguo del 25 %"
