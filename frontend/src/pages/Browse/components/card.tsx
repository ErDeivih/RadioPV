/* eslint-disable jsx-a11y/alt-text */
import { FC, memo, useMemo } from 'react';

import { Link } from 'react-router-dom';

// Interfaces
import type { Category } from '../../../interfaces/categories';

/**
 * COLOR DE CADA CATEGORÍA, FIJO Y PROPIO
 * -------------------------------------
 * Antes todas las tarjetas salían **del mismo rojo**: el color se sacaba analizando la imagen de la
 * tarjeta, y esa imagen es el mismo icono de relleno en todas, así que el análisis devolvía siempre
 * el mismo valor. El resultado era una pantalla de 23 tarjetas idénticas, que parece rota.
 *
 * Spotify da a cada género su color y no lo cambia nunca: eso es lo que se hace aquí, con una paleta
 * sacada de las suyas y un reparto por nombre (el mismo género cae siempre en el mismo color, sin
 * guardar nada en la base).
 */
const PALETA = [
  '#dc148c', // rosa
  '#e8115b', // frambuesa
  '#8d67ab', // morado
  '#7358ff', // violeta
  '#1e3264', // azul noche
  '#537aa1', // azul gris
  '#158a08', // verde hoja
  '#4a8521', // verde oliva
  '#af2896', // magenta
  '#e13300', // naranja rojizo
  '#ba5d07', // naranja
  '#8c1932', // granate
  '#0d73ec', // azul
  '#056952', // verde azulado
  '#777777', // gris
  '#503750', // ciruela
];

export const colorDeCategoria = (semilla: string): string => {
  let hash = 0;
  for (let i = 0; i < semilla.length; i += 1) {
    hash = (hash * 31 + semilla.charCodeAt(i)) % 100000;
  }
  return PALETA[hash % PALETA.length];
};

export const BrowseCard: FC<{ category: Category }> = memo(({ category }) => {
  // El color depende del id (`genre:techhouse`, `language:es`…), que no cambia nunca.
  const color = useMemo(() => colorDeCategoria(category.id || category.name), [category.id, category.name]);

  return (
    <div>
      <Link to={`/genre/${category.id}`} className='browse-card'>
        <div className='browse-card-container' style={{ backgroundColor: color }}>
          {category.icons.length ? <img loading='lazy' alt='' src={category.icons[0].url} /> : null}
          <span>
            {category.name}
            {category.count != null ? (
              <em className='browse-card-count'>
                {/* El recuento separado y con separador de miles: antes salía pegado al nombre
                    («Pop2078»), que se lee como si fuera parte del título. */}
                {' · '}
                {Number(category.count).toLocaleString('es-ES')}
              </em>
            ) : null}
          </span>
        </div>
      </Link>
    </div>
  );
});

BrowseCard.displayName = 'BrowseCard';
