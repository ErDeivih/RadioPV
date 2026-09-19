import { describe, expect, it } from 'vitest';

import { nombreDeFichero, puedeElegirCarpeta } from '../services/descargas';

/**
 * Descargar música a una carpeta: el nombre del fichero.
 *
 * Parece una tontería y no lo es: en el catálogo hay títulos con «/», «:», «?», comillas y
 * asteriscos (vienen de YouTube, que los permite). Un nombre con «/» en Windows crea una CARPETA
 * en vez de un fichero, y al escribir el segundo se pierde. Y si el nombre se queda vacío tras
 * limpiar, el fichero no se puede escribir.
 */
describe('nombre de fichero al descargar', () => {
  it('usa el formato «Artista - Título.mp3»', () => {
    expect(nombreDeFichero('Bad Bunny', 'Tití Me Preguntó')).toBe('Bad Bunny - Tití Me Preguntó.mp3');
  });

  it('quita los caracteres que rompen el sistema de ficheros', () => {
    expect(nombreDeFichero('AC/DC', 'Back in Black')).toBe('ACDC - Back in Black.mp3');
    expect(nombreDeFichero('Bizarrap', 'Vol. 52/66: Quevedo?')).toBe(
      'Bizarrap - Vol. 5266 Quevedo.mp3'
    );
    expect(nombreDeFichero('A|B', 'C*D"E<F>G')).toBe('AB - CDEFG.mp3');
  });

  it('no deja nombres vacíos ni solo espacios', () => {
    expect(nombreDeFichero('', '')).toBe('cancion.mp3');
    expect(nombreDeFichero('///', '***')).toBe('cancion.mp3');
  });

  it('recorta los nombres larguísimos (Windows no pasa de 255 en la ruta entera)', () => {
    const largo = nombreDeFichero('A'.repeat(200), 'B'.repeat(200));
    expect(largo.length).toBeLessThanOrEqual(124);
    expect(largo.endsWith('.mp3')).toBe(true);
  });

  it('si el navegador no deja elegir carpeta, se dice (en el móvil no se puede)', () => {
    // En jsdom no existe `showDirectoryPicker`, así que la respuesta debe ser «no».
    expect(puedeElegirCarpeta()).toBe(false);
  });
});
