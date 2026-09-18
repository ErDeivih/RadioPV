import { Flex } from 'antd';
import { useAppSelector } from '../../../../../store/store';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Play } from '../../../../../components/Icons';

/**
 * "Lo más escuchado este mes", pero como LISTA y no como cinco canciones sueltas.
 *
 * Antes esto pintaba cinco filas de canciones directamente en el perfil. El perfil es la
 * biblioteca, y ahí lo que se ofrece son listas: se enseña una tarjeta que dice cuántas
 * canciones tiene y se entra en ella (`/users/:id/tracks`), que es donde están las canciones.
 * Así la canción suelta aparece como consecuencia de entrar en una lista, no antes.
 */
export const Songs = () => {
  const { t } = useTranslation(['profile']);

  const user = useAppSelector((state) => state.profile.user);
  const songs = useAppSelector((state) => state.profile.songs);

  if (!user || !songs || songs.length === 0) return null;

  return (
    <div style={{ marginTop: 10 }}>
      <h1 className='playlist-header'>{t('Top tracks this month')}</h1>

      <Link to={`/users/${user.id}/tracks`} className='profile-top-list'>
        <span className='profile-top-list__play' aria-hidden='true'>
          <Play />
        </span>
        <span className='profile-top-list__text'>
          <b>{t('Your most played this month')}</b>
          <small>
            {songs.length} {songs.length === 1 ? t('song') : t('songs')} · {t('Only visible to you')}
          </small>
        </span>
      </Link>
    </div>
  );
};
