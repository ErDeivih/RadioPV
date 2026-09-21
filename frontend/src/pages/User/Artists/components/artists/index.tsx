import { memo } from 'react';

// Components
import { GridItemList } from '../../../../../components/Lists/list';

// Redux
import { useAppSelector } from '../../../../../store/store';
import { useTranslation } from 'react-i18next';

export const ArtistsProfileSection = memo(() => {
  const [t] = useTranslation(['profile']);
  const artists = useAppSelector((state) => state.profile.artists);

  return (
    <div>
      <div>
        <GridItemList
          multipleRows
          items={artists}
          title={t('Top artists this month')}
          subtitle={t('Only visible to you')}
        />

        {/* Sin artistas escuchados la pantalla quedaba en blanco: sólo el título. Se dice. */}
        {!artists?.length ? (
          <p className='empty-state'>
            Todavía no hay artistas que enseñar: aparecen aquí los que más escuchas cada mes.
          </p>
        ) : null}
      </div>
    </div>
  );
});
