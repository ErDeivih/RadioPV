// I18n
import { useTranslation } from 'react-i18next';
import { useAppSelector } from '../../../../store/store';
import { FC, memo } from 'react';
import { ARTISTS_DEFAULT_IMAGE } from '../../../../constants/spotify';

export const UserHeader: FC<{ color: string }> = memo((props) => {
  const { t } = useTranslation(['profile']);
  const user = useAppSelector((state) => state.profile.user);

  const toggleHideExplicit = (e: React.ChangeEvent<HTMLInputElement>) => {
    localStorage.setItem('radiopv_hide_explicit', e.target.checked ? '1' : '0');
    window.location.reload(); // recarga para que el filtro se aplique a las filas ya cargadas
  };

  return (
    <div className='profile-header'>
      <div
        className='profile-header-cover'
        style={{
          backgroundColor: props.color,
        }}
      ></div>

      <div className='profile-header-background'></div>
      <div className='profile-header-content'>
        {/* Image section */}
        <div></div>
        <div className='profile-img-container'>
          <div className='profile-img'>
            <div
              style={{
                borderRadius: 4,
                height: '100%',
                width: '100%',
              }}
            >
              <img
                src={
                  user?.images && user.images.length ? user.images[0].url : ARTISTS_DEFAULT_IMAGE
                }
                alt={user?.display_name}
              />
            </div>
          </div>
        </div>

        {/* Text Section */}
        <div className='profile-header-text'>
          <span className='type'>{t('Profile')}</span>

          <span className='profile-header-name-container'>
            <h1>{user?.display_name}</h1>
          </span>

          <div className='profile-header-details-container'>
            {/* `followers` was removed from GET /me in Feb 2026, so only show it when present. */}
            {user?.followers?.total != null ? (
              <span data-encore-id='text'>
                {user.followers.total} {t('Followers')}
              </span>
            ) : null}
            <label style={{ marginLeft: 14, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <input
                type='checkbox'
                checked={localStorage.getItem('radiopv_hide_explicit') === '1'}
                onChange={toggleHideExplicit}
              />
              Ocultar contenido explícito
            </label>
          </div>
        </div>
      </div>
    </div>
  );
});
