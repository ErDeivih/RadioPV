import { memo } from 'react';
import { Link } from 'react-router-dom';
import { Button } from 'antd';

// Components
import { GridItemList } from '../../../../../components/Lists/list';

// Redux
import { useAppSelector } from '../../../../../store/store';
import { useTranslation } from 'react-i18next';

export const PlaylistsProfileSection = memo(() => {
  const [t] = useTranslation(['profile']);
  const playlists = useAppSelector((state) => state.profile.playlists);

  return (
    <div>
      {/* Importar una lista de Spotify. Va aquí —donde se ven y se crean las listas— porque es donde
        * se busca: el usuario lo pidió como «una opción donde pasar una playlist de Spotify y que se
        * cree igual en mi aplicación». */}
      <div className='importar-atajo'>
        <Link to='/importar'>
          <Button size='large'>Importar una lista de Spotify</Button>
        </Link>
      </div>

      <GridItemList multipleRows items={playlists} title={t('Public playlists')} />

      {/* Sin listas públicas la pantalla quedaba en blanco: sólo el título y nada más. Se dice. */}
      {!playlists?.length ? (
        <p className='empty-state'>
          No hay listas públicas. Las listas que crees y marques como públicas aparecerán aquí.
        </p>
      ) : null}
    </div>
  );
});
