import { Space } from 'antd';
import { FC, RefObject } from 'react';
import Chip from '../../../../components/Chip';
import { PageHeader } from '../../../../components/Layout/components/Header';

// Utils
import { useTranslation } from 'react-i18next';

// Redux
import { useAppSelector } from '../../../../store/store';
import { useNavigate, useParams } from 'react-router-dom';

interface HomeHeaderProps {
  color: string;
  container: RefObject<HTMLDivElement | null>;
  sectionContainer: RefObject<HTMLDivElement | null>;
}

// Las listas primero y las canciones al final: la música se escucha en listas, así que el orden
// de las pestañas también lo dice. «Canciones» sigue estando, pero es la última.
const SECTIONS = ['ALL', 'PLAYLISTS', 'ALBUMS', 'ARTISTS', 'TRACKS'];

/**
 * Filtros de resultados: Todo / Artistas / Canciones / Álbumes / Listas.
 *
 * POR QUÉ ESTÁ APARTE
 * -------------------
 * Estos botones vivían sólo dentro de `.nav-header`, la barra fija superior. En el móvil esa
 * barra arranca con `visibility: hidden` y no se hace visible hasta que te desplazas, así que
 * **en un teléfono los filtros de búsqueda no se veían al llegar a la página**: el usuario sólo
 * veía la pestaña «Todo» y no tenía forma de saber que existían las demás. Medido con la
 * auditoría: los cinco chips salían como invisibles en móvil.
 *
 * Ahora el mismo componente se pinta en dos sitios y el CSS deja uno u otro según la pantalla:
 *  · móvil   → en una barra propia, justo debajo de la cabecera, siempre visible;
 *  · escritorio → dentro de la barra fija de arriba, como antes.
 */
export const SearchFilterChips: FC = () => {
  const navigate = useNavigate();
  const [t] = useTranslation(['home']);

  const params = useParams<{ search: string }>();
  const section = useAppSelector((state) => state.search.section);

  return (
    <Space className='search-filters' size={10} wrap>
      {SECTIONS.map((item) => (
        <Chip
          key={item}
          text={t(item)}
          active={section === item}
          onClick={() =>
            navigate(`/search/${params.search}/${item === 'ALL' ? '' : item?.toLowerCase()}`)
          }
        />
      ))}
    </Space>
  );
};

export const SearchHeader: FC<HomeHeaderProps> = (props) => {
  const { container, sectionContainer, color } = props;

  return (
    <PageHeader
      color={color}
      activeHeider={20}
      container={container}
      sectionContainer={sectionContainer}
    >
      <div className='search-filters-header'>
        <SearchFilterChips />
      </div>
    </PageHeader>
  );
};
