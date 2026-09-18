import { memo, useMemo, useState } from 'react';

import TopSong from './song';
import { Col, Row } from 'antd';

// Redux
import { useAppSelector } from '../../../../store/store';

// Utils
import { useTranslation } from 'react-i18next';
import { playerService } from '../../../../services/player';
import { Play } from '../../../../components/Icons';

export const ArtistTopTracks = memo(() => {
  const [t] = useTranslation(['artist']);
  const [showAll, setShowAll] = useState(false);
  const topSongs = useAppSelector((state) => state.artist.topTracks);

  const items = useMemo(() => {
    if (showAll) {
      return topSongs;
    }
    return topSongs.slice(0, 5);
  }, [showAll, topSongs]);

  // La lista del artista se reproduce ENTERA con un solo toque: el reproductor ya sabe resolver
  // `radiopv:artist:<nombre>` a sus canciones más escuchadas, así que esto llena la cola con
  // ellas en vez de dejar cinco canciones sueltas cada una con su botón.
  const artista = topSongs[0]?.artists?.[0]?.name;
  const reproducirTodo = () => {
    if (artista) void playerService.startPlayback({ context_uri: `radiopv:artist:${artista}` });
  };

  if (!topSongs.length) {
    return null;
  }

  return (
    <div style={{ margin: 10 }}>
      <div className='flex items-center justify-between'>
        <h1 className='playlist-header'>{t('Popular')}</h1>
        <button
          aria-label={t('Play')}
          title={t('Play')}
          onClick={reproducirTodo}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 40,
            height: 40,
            border: 'none',
            borderRadius: '50%',
            cursor: 'pointer',
            background: '#1ed760',
            color: '#000',
          }}
        >
          <Play />
        </button>
      </div>
      <Row>
        <Col span={24}>
          <div>
            {items.map((song, index) => (
              <TopSong key={song.uri} song={song} index={index} />
            ))}
          </div>
        </Col>
      </Row>
      <button className='showMore' onClick={() => setShowAll((s) => !s)}>
        <span>{showAll ? t('Show less') : t('Show more')}</span>
      </button>
    </div>
  );
});
