import { FC, memo, useMemo } from 'react';
import { Pause, Play } from '../../../../Icons';
import { useAppSelector } from '../../../../../store/store';
import { playerService } from '../../../../../services/player';
import { Episode } from '../../../../../interfaces/episode';
import useIsMobile from '../../../../../utils/isMobile';
import { useTranslation } from 'react-i18next';

interface QueueSongDetailsProps {
  song: Spotify.Track | Episode;
  isPlaying: boolean;
  /** Posición dentro de la cola. Si viene, la fila muestra los botones de quitar y reordenar. */
  indice?: number;
}

/** Botones de la fila de la cola: quitar y mover arriba/abajo.
 *
 *  Antes el panel de la cola sólo pintaba: no se podía quitar ni reordenar nada. Se usan flechas
 *  en vez de arrastrar porque en el móvil son mucho más fiables (y se pueden probar). */
const BotonesCola: FC<{ indice: number; total: number }> = ({ indice, total }) => {
  const { t } = useTranslation(['playingBar']);

  const parar = (e: React.MouseEvent) => {
    // Sin esto, pulsar un botón también dispararía el clic de la fila (que reproduce).
    e.stopPropagation();
  };

  return (
    <div className='cola-botones'>
      <button
        title={t('Move up')}
        aria-label={t('Move up')}
        disabled={indice === 0}
        onClick={(e) => {
          parar(e);
          void playerService.moveInQueue(indice, indice - 1);
        }}
      >
        <svg viewBox='0 0 16 16' width='14' height='14' aria-hidden='true'>
          <path d='M8 1.5 14.5 8h-4v6.5h-5V8h-4L8 1.5z' />
        </svg>
      </button>

      <button
        title={t('Move down')}
        aria-label={t('Move down')}
        disabled={indice === total - 1}
        onClick={(e) => {
          parar(e);
          void playerService.moveInQueue(indice, indice + 1);
        }}
      >
        <svg viewBox='0 0 16 16' width='14' height='14' aria-hidden='true'>
          <path d='M8 14.5 1.5 8h4V1.5h5V8h4L8 14.5z' />
        </svg>
      </button>

      <button
        title={t('Remove from queue')}
        aria-label={t('Remove from queue')}
        onClick={(e) => {
          parar(e);
          void playerService.removeFromQueue(indice);
        }}
      >
        <svg viewBox='0 0 16 16' width='14' height='14' aria-hidden='true'>
          <path d='M2.5 2.5 13.5 13.5M13.5 2.5 2.5 13.5' stroke='currentColor' strokeWidth='1.6' fill='none' strokeLinecap='round' />
        </svg>
      </button>
    </div>
  );
};

const QueueSongDetails: FC<QueueSongDetailsProps> = memo(({ song, isPlaying, indice }) => {
  const isMobile = useIsMobile();
  const queue = useAppSelector((state) => state.queue.queue);
  const isPaused = useAppSelector((state) => state.spotify.state?.paused);
  const enCola = typeof indice === 'number';

  const onClick = async () => {
    if (!isPaused && isPlaying) {
      return playerService.pausePlayback();
    }
    if (isPlaying) {
      return playerService.startPlayback();
    } else {
      const index = queue.findIndex((q) => q.id === song.id);
      return playerService.startPlayback({ uris: queue.slice(index).map((q_1) => q_1.uri) });
    }
  };

  const image = useMemo(() => {
    if (song.type === 'track') {
      return song.album?.images?.[0]?.url ?? '';
    }

    if (song.type === 'episode') {
      const episode = song as Episode;
      return episode.images?.[0]?.url ?? episode.show?.images?.[0]?.url ?? '';
    }

    return '';
  }, [song]);

  const artists = useMemo(() => {
    if (song.type === 'track') {
      return song.artists
        .slice(0, 3)
        .map((a) => a.name)
        .join(', ');
    }

    if (song.type === 'episode') {
      return (song as any as Episode).show?.publisher ?? (song as any as Episode).show?.name ?? '';
    }

    return '';
  }, [song]);

  return (
    <div
      className='queue-song'
      onClick={isMobile ? onClick : undefined}
      onDoubleClick={!isMobile ? onClick : undefined}
    >
      <div className=' flex flex-row items-center'>
        <div className='queue-song-image-container'>
          {!isMobile ? (
            <div className='queue-song-overlay' onClick={onClick}>
              {!isPaused && isPlaying ? <Pause /> : <Play />}
            </div>
          ) : null}

          <img alt='Album Cover' className='album-cover' src={image} />
        </div>
        <div id='song-and-artist-name'>
          <p
            title={song.name}
            className={`text-white font-bold song-title ${isPlaying ? 'active' : ''}`}
          >
            {song.name}
          </p>
          <p className='text-gray-200 song-artist' title={artists}>
            {artists}
          </p>
        </div>

        {enCola ? <BotonesCola indice={indice!} total={queue.length} /> : null}
      </div>
    </div>
  );
});

export default QueueSongDetails;
