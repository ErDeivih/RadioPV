import { PlayCircle } from './PlayCircle';
import { TrackActionsWrapper } from '../Actions/TrackActions';
import { AlbumActionsWrapper } from '../Actions/AlbumActions';
import { ArtistActionsWrapper } from '../Actions/ArtistActions';
import { PlayistActionsWrapper } from '../Actions/PlaylistActions';

// Interfaces
import type { Track } from '../../interfaces/track';
import type { Album } from '../../interfaces/albums';
import type { Artist } from '../../interfaces/artist';
import type { Playlist } from '../../interfaces/playlists';

// Utils
import { useTranslation } from 'react-i18next';

// Redux
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../../store/store';

// Constants
import { PLAYLIST_DEFAULT_IMAGE } from '../../constants/spotify';
import { uiActions } from '../../store/slices/ui';
import { useCallback } from 'react';

/**
 * Portada de una tarjeta: una imagen, o el MOSAICO 2Ã—2 cuando hay cuatro.
 *
 * POR QUÃ‰ EXISTE
 * --------------
 * Las listas que genera la aplicaciÃ³n no tienen portada propia, asÃ­ que salÃ­an **todas con el mismo
 * icono gris de relleno**: en la portada se veÃ­an seis tarjetas idÃ©nticas y parecÃ­a que faltaban las
 * imÃ¡genes. Spotify resuelve esto con un mosaico de las carÃ¡tulas de las primeras canciones, que es
 * lo que se pinta aquÃ­ (la API manda hasta cuatro en `collage`).
 */
export const Portada = ({ images, title, rounded }: { images: string[]; title: string; rounded?: boolean }) => {
  if (images.length >= 4) {
    return (
      <div className='portada-mosaico'>
        {images.slice(0, 4).map((url, i) => (
          <img key={`${url}-${i}`} src={url} alt='' loading='lazy' />
        ))}
      </div>
    );
  }
  return (
    <img
      src={images[0]}
      alt={title}
      className={rounded ? 'rounded' : ''}
      style={{ borderRadius: 5, width: '100%' }}
    />
  );
};

const Card = ({
  uri,
  title,
  images,
  rounded,
  description,
  onClick,
  context,
}: {
  uri: string;
  images: string[];
  title: string;
  rounded?: boolean;
  description: string;
  onClick: () => void;
  context: { context_uri?: string; uris?: string[] };
}) => {
  const paused = useAppSelector((state) => state.spotify.state?.paused);
  const contextUri = useAppSelector((state) => state.spotify.state?.context?.uri);
  const isCurrent = contextUri === uri;

  return (
    <div
      onClick={onClick}
      style={{ cursor: 'pointer' }}
      className='playlist-card relative rounded-lg overflow-hidden  hover:bg-spotify-gray-lightest transition'
    >
      <div
        style={{ position: 'relative' }}
        className='aspect-square md:aspect-w-1 md:aspect-h-1/2 lg:aspect-w-1 lg:aspect-h-3/4 xl:aspect-w-1 xl:aspect-h-4/5 p-4'
      >
        <Portada images={images} title={title} rounded={rounded} />
        <div
          className={`circle-play-div transition translate-y-1/4 ${
            isCurrent && !paused ? 'active' : ''
          }`}
        >
          <PlayCircle image={images[0]} isCurrent={isCurrent} context={context} />
        </div>
      </div>
      <div className='playlist-card-info'>
        <h3 className='text-md font-semibold text-white'>{title}</h3>
        <p>{description}</p>
      </div>
    </div>
  );
};

export const ArtistCard = ({
  item,
  onClick,
  getDescription,
}: {
  item: Artist;
  onClick?: () => void;
  getDescription?: (item: Artist) => string;
}) => {
  const navigate = useNavigate();
  const [t] = useTranslation(['artist']);

  const title = item.name;
  const description = getDescription ? getDescription(item) : t('Artist');

  return (
    <ArtistActionsWrapper artist={item} trigger={['contextMenu']}>
      <div onClick={onClick}>
        <Card
          rounded
          title={title}
          uri={item.uri}
          description={description}
          images={[item.images[0]?.url]}
          context={{ context_uri: item.uri }}
          onClick={() => navigate(`/artist/${item.id}`)}
        />
      </div>
    </ArtistActionsWrapper>
  );
};

export const AlbumCard = ({
  item,
  onClick,
  getDescription,
}: {
  item: Album;
  onClick?: () => void;
  getDescription?: (playlist: Album) => string;
}) => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.auth.user);

  const onNavigate = useCallback(() => {
    if (!user) {
      return dispatch(uiActions.openLoginModal(item.images[0].url));
    }
    navigate(`/album/${item.id}`);
  }, [user, navigate, item.id, item.images, dispatch]);

  const title = item.name;

  const description = getDescription
    ? getDescription(item)
    : item.artists
        .slice(0, 3)
        .map((artist) => artist.name)
        .join(', ');

  return (
    <AlbumActionsWrapper album={item} trigger={['contextMenu']}>
      <div onClick={onClick}>
        <Card
          title={title}
          uri={item.uri}
          onClick={onNavigate}
          description={description}
          images={[item.images[0]?.url]}
          context={{ context_uri: item.uri }}
        />
      </div>
    </AlbumActionsWrapper>
  );
};

export const PlaylistCard = ({
  item,
  onClick,
  getDescription,
}: {
  item: Playlist;
  onClick?: () => void;
  getDescription?: (playlist: Playlist) => string;
}) => {
  const navigate = useNavigate();
  const [t] = useTranslation(['playlist']);

  const title = item.name;
  // Feb 2026 renamed the playlist track-count field `tracks` â†’ `items`; fall back so we never
  // render "undefined songs" regardless of which endpoint the playlist came from.
  const trackTotal = (item as any).tracks?.total ?? (item as any).items?.total;
  const description = getDescription
    ? getDescription(item)
    : trackTotal === undefined
      ? ''
      : trackTotal + ' ' + t(trackTotal === 1 ? 'song' : 'songs');

  return (
    <PlayistActionsWrapper playlist={item} trigger={['contextMenu']}>
      <div onClick={onClick}>
        <Card
          title={title}
          uri={item.uri}
          description={description}
          context={{ context_uri: item.uri }}
          onClick={() => navigate(`/playlist/${item.id}`)}
          images={item.images && item.images.length ? item.images.map((i) => i.url) : [PLAYLIST_DEFAULT_IMAGE]}
        />
      </div>
    </PlayistActionsWrapper>
  );
};

export const TrackCard = ({
  item,
  getDescription,
  onClick,
}: {
  item: Track;
  onClick?: () => void;
  getDescription?: (track: Track) => string;
}) => {
  const navigate = useNavigate();
  const description = getDescription ? getDescription(item) : item.album.name;

  return (
    <TrackActionsWrapper track={item} trigger={['contextMenu']}>
      <div onClick={onClick}>
        <Card
          uri={item.uri}
          title={item.name}
          description={description}
          context={{ uris: [item.uri] }}
          images={[item.album.images[0]?.url]}
          onClick={() => navigate(`/album/${item.album.id}`)}
        />
      </div>
    </TrackActionsWrapper>
  );
};
