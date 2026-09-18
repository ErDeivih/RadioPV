import SongView from './song';
import { useTranslation } from 'react-i18next';
import { useAppSelector } from '../../../../../store/store';
import { Link, useParams } from 'react-router-dom';

/**
 * Canciones encontradas.
 *
 * Con `limite` se enseña sólo un adelanto y un enlace a la pestaña «Canciones», donde están
 * todas. En la vista de resultados general se usa `limite={4}`: las canciones sueltas son el
 * último recurso, no lo primero que se ve al buscar.
 */
export const SearchedSongs = ({ limite }: { limite?: number }) => {
  const { t } = useTranslation(['search']);
  const { search } = useParams<{ search: string }>();
  const songs = useAppSelector((state) => state.search.songs);

  if (!songs || songs.length === 0) return null;

  const recortado = typeof limite === 'number' && songs.length > limite;
  const visibles = recortado ? songs.slice(0, limite) : songs;

  return (
    <div className='search-songs-container'>
      <h1 className='section-title'>{t('Songs')}</h1>

      <div>
        {visibles.map((song, index) => (
          <SongView song={song} key={song.id} index={index} />
        ))}
      </div>

      {recortado && (
        <Link className='showMore' to={`/search/${encodeURIComponent(search ?? '')}/tracks`}>
          <span>
            {t('See all songs')} ({songs.length})
          </span>
        </Link>
      )}
    </div>
  );
};
