import { memo, useCallback } from 'react';
import { useAppDispatch, useAppSelector } from '../../../store/store';
import { GridItemList } from '../../../components/Lists/list';
import { genreActions } from '../../../store/slices/genre';
import tinycolor from 'tinycolor2';

export const GenreContent = memo((props: { color: string }) => {
  const dispatch = useAppDispatch();
  const tracks = useAppSelector((state) => state.genre.playlists);   // ahora Track[]
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
        maxHeight: 260,
        overflow: 'auto',
        background: `linear-gradient(${
          tinycolor(props.color).isLight()
            ? tinycolor(props.color).darken(20)
            : tinycolor(props.color).darken(12)
        } 0, rgb(18 18 18) 100%), var(--background-noise)`,
      }}
      className='genre-list'
    >
      <GridItemList
        title='Canciones'
        items={tracks as any}
        extra={
          tracks.length < total ? (
            <button className='showMore' onClick={loadMore}>
              <span>Mostrar más</span>
            </button>
          ) : undefined
        }
      />
    </div>
  );
});

GenreContent.displayName = 'GenreContent';

export default GenreContent;
