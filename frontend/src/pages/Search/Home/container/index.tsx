import { FC } from 'react';

import { Col, Row } from 'antd';

import { SearchedSongs } from '../components/songs';
import { TopResult } from '../components/topResult';
import { AlbumsSearchSection } from '../components/albums';
import { ArtistsSearchSection } from '../components/artists';
import { PlaylistsSearchSection } from '../components/playlists';

interface SearchPageProps {
  container: React.RefObject<HTMLDivElement | null>;
}

/**
 * Resultados de búsqueda, en el orden en que se leen y se usan.
 *
 * ORDEN: LISTAS PRIMERO, CANCIONES AL FINAL.
 * ------------------------------------------
 * Antes las canciones sueltas iban ARRIBA, ocupando media pantalla al lado del resultado más
 * relevante, y las listas y los álbumes quedaban debajo: lo primero que veías al buscar un
 * artista era una lista plana de canciones sueltas de sitios distintos, sin saber de dónde sale
 * cada una ni cómo escucharlas seguidas. Como la música se escucha en listas, aquí van primero
 * las listas, los álbumes y los artistas (cada uno es una lista de su música) y las canciones
 * quedan al final, recortadas a cuatro: para verlas todas está su pestaña. Una canción se
 * escucha entrando en la lista a la que pertenece.
 */
export const SearchPageContainer: FC<SearchPageProps> = (props) => {
  return (
    <Row gutter={[16, 16]} style={{ paddingBottom: 20 }}>
      <Col span={24} lg={9}>
        <TopResult />
      </Col>

      <Col span={24} lg={15}>
        <ArtistsSearchSection />
      </Col>

      <Col span={24}>
        <PlaylistsSearchSection />
      </Col>

      <Col span={24}>
        <AlbumsSearchSection />
      </Col>

      <Col span={24}>
        {/* Cuatro nada más: es un adelanto, no el contenido principal. */}
        <SearchedSongs limite={4} />
      </Col>
    </Row>
  );
};

export default SearchPageContainer;
