import { FC, useRef } from 'react';

import { SearchFilterChips, SearchHeader } from './header';
import { Outlet } from 'react-router-dom';
import { DEFAULT_PAGE_COLOR } from '../../../constants/spotify';

// Constants

interface SearchPageProps {
  container: React.RefObject<HTMLDivElement | null>;
}

export const SearchContainer: FC<SearchPageProps> = (props) => {
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div ref={ref}>
      <SearchHeader color={DEFAULT_PAGE_COLOR} sectionContainer={ref} container={props.container} />

      {/*
        Los filtros (Todo / Artistas / Canciones / Álbumes / Listas) van AQUÍ en móvil, fuera de la
        barra fija, porque esa barra no se ve hasta que te desplazas y los filtros quedaban
        inalcanzables. En escritorio esta barra se oculta por CSS y los chips se pintan dentro de
        la cabecera, como siempre. Ver el comentario de `SearchFilterChips`.
      */}
      <div className='search-filters-bar'>
        <SearchFilterChips />
      </div>

      <div className='Search-Page'>
        <Outlet />
      </div>
    </div>
  );
};

export default SearchContainer;
