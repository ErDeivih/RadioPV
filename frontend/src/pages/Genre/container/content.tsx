import { memo, useCallback } from 'react';
import { useAppDispatch, useAppSelector } from '../../../store/store';
import { GridItemList } from '../../../components/Lists/list';
import { genreActions } from '../../../store/slices/genre';
import tinycolor from 'tinycolor2';
import { useTranslation } from 'react-i18next';

/**
 * Contenido de la página de género (o de era / estado de ánimo).
 *
 * ORDEN: PRIMERO LAS LISTAS, DESPUÉS LAS CANCIONES.
 * ------------------------------------------------
 * Antes esto era sólo una rejilla de canciones sueltas del género. Como la música se escucha en
 * listas, primero van las listas que la aplicación genera para ese género (`Top pop`,
 * `Top bachata`…) y después las canciones, con su «Mostrar más». Se entra en la lista y desde
 * dentro se escuchan las canciones.
 */
export const GenreContent = memo((props: { color: string }) => {
  const dispatch = useAppDispatch();
  const [t] = useTranslation(['search']);
  const tracks = useAppSelector((state) => state.genre.playlists);   // ahora Track[]
  const listas = useAppSelector((state) => state.genre.listas);
  const id = useAppSelector((state) => state.genre.category?.id);
  const total = useAppSelector((state) => state.genre.total);

  const loadMore = useCallback(() => {
    if (!id) return;
    dispatch(genreActions.fetchMoreGenre({ id, offset: tracks.length }));
  }, [dispatch, id, tracks.length]);

  return (
    <div
      style={{
        padding: 20,
        paddingTop: 30,
        /* SIN `maxHeight` NI SCROLL PROPIO. Aquí había `maxHeight: 260, overflow: 'auto'`: la
         * página metía 7.137 px de listas y canciones dentro de una ventana de 260 px, así que en
         * la pantalla sólo se veía el título, «Listas de este género» y una tarjeta — el resto
         * exigía desplazar una cajita diminuta. Medido con el navegador. Ahora manda el scroll de
         * la página, que es lo que hace Spotify. */
        background: `linear-gradient(${
          tinycolor(props.color).isLight()
            ? tinycolor(props.color).darken(20)
            : tinycolor(props.color).darken(12)
        } 0, rgb(18 18 18) 100%), var(--background-noise)`,
      }}
      className='genre-list'
    >
      {listas.length > 0 ? (
        <div style={{ marginBottom: 24 }}>
          <GridItemList title={t('Lists of this genre')} items={listas as any} />
        </div>
      ) : null}

      <GridItemList
        title={t('Songs')}
        items={tracks as any}
        extra={
          tracks.length < total ? (
            <button className='showMore' onClick={loadMore}>
              <span>{t('Show more')}</span>
            </button>
          ) : undefined
        }
      />
    </div>
  );
});

GenreContent.displayName = 'GenreContent';

export default GenreContent;
