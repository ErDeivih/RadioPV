import { useTranslation } from 'react-i18next';
import { NowPlayingLayout } from '../layout';
import { useAppSelector } from '../../../../../store/store';
import { playerService } from '../../../../../services/player';

import QueueSongDetailsProps from './SongDetails';

const NowPlaying = () => {
  const [t] = useTranslation(['playingBar']);
  const song = useAppSelector(
    (state) => state.spotify.state?.track_window.current_track,
    (a, b) => a?.id === b?.id
  );
  if (!song) return null;

  return (
    <div>
      <p className='playing-section-title'>{t('Now playing')}</p>
      <div style={{ margin: 5 }}>
        <QueueSongDetailsProps song={song} isPlaying={true} />
      </div>
    </div>
  );
};

const Queueing = () => {
  const [t] = useTranslation(['playingBar']);
  const queue = useAppSelector((state) => state.queue.queue);

  if (!queue || !queue.length) return null;

  return (
    <div style={{ marginTop: 30 }}>
      <div className='flex items-center justify-between'>
        <p className='playing-section-title'>{t('Next')}</p>
        <div className='flex items-center'>
          {/* El "Flow" sólo entraba solo, al agotarse la cola: ahora se puede pedir. */}
          <button
            className='cola-vaciar'
            title={t('Start radio')}
            aria-label={t('Start radio')}
            onClick={() => void playerService.startFlow()}
          >
            {t('Start radio')}
          </button>
          {/* Antes la cola sólo se podía mirar: no había forma de quitarla entera. */}
          <button
            className='cola-vaciar'
            title={t('Clear queue')}
            aria-label={t('Clear queue')}
            onClick={() => void playerService.clearQueue()}
          >
            {t('Clear queue')}
          </button>
        </div>
      </div>

      <div style={{ margin: 5 }}>
        {queue.map((q, index) => (
          // @ts-ignore
          <QueueSongDetailsProps key={`${q.id}-${index}`} song={q} indice={index} />
        ))}
      </div>
    </div>
  );
};

export const Queue = () => {
  const [t] = useTranslation(['playingBar']);

  return (
    <NowPlayingLayout title={t('Queue')}>
      <div style={{ marginTop: 20 }}>
        <NowPlaying />
        <Queueing />
      </div>
    </NowPlayingLayout>
  );
};
