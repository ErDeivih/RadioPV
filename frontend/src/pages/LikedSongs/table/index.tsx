// Components
import { Divider } from 'antd';
import SongView from './Song';
import { PlaylistTableHeader } from './header';
import { PlaylistControls } from '../controls';

// Redux
import { likedSongsActions } from '../../../store/slices/likedSongs';
import { useAppDispatch, useAppSelector } from '../../../store/store';

// Constants
import { DEFAULT_PAGE_COLOR } from '../../../constants/spotify';

// Interfaces
import { memo, type FC } from 'react';
import InfiniteScroll from 'react-infinite-scroll-component';

interface LikedSongsListProps {
  color: string;
}

export const LikedSongsList: FC<LikedSongsListProps> = memo(({ color }) => {
  const dispatch = useAppDispatch();
  const total = useAppSelector((state) => state.likedSongs.total);
  const loading = useAppSelector((state) => state.likedSongs.loading);
  const tracks = useAppSelector((state) => state.likedSongs.items);

  return (
    <div
      className='playlist-list'
      style={{
        maxHeight: 323,
        background: `linear-gradient(${color} -50%, ${DEFAULT_PAGE_COLOR} 90%)`,
      }}
    >
      <PlaylistControls />
      {!!total ? (
        <div className='playlist-table'>
          <PlaylistTableHeader />
        </div>
      ) : (
        <Divider />
      )}

      {/* Sin canciones guardadas la página se quedaba EN BLANCO: ni lista, ni mensaje, ni pista de
       *  qué hacer. No era un fallo de datos (de verdad no había ninguna canción guardada), pero
       *  desde el móvil parecía que la aplicación estaba rota. */}
      {!total && !loading ? (
        <p className='empty-state'>
          Todavía no has guardado ninguna canción. Pulsa el corazón de una canción y aparecerá aquí.
        </p>
      ) : null}

      <InfiniteScroll
        loader={null}
        scrollThreshold={0.5}
        dataLength={tracks.length}
        next={() => {
          dispatch(likedSongsActions.fetchMore());
        }}
        hasMore={tracks.length < total}
      >
        {!!total ? (
          <div style={{ paddingBottom: 30 }}>
            {tracks.map((song, index) => (
              <SongView song={song} key={`${song.added_at}-${song.track.id}`} index={index} />
            ))}
          </div>
        ) : null}
      </InfiniteScroll>
    </div>
  );
});
