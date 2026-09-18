import { useCallback } from 'react';

import { Button, Popconfirm, Space } from 'antd';
import { Link } from 'react-router-dom';
import { CloseIcon } from '../../../Icons';
import { WhiteButton } from '../../../Button';

// Utils
import { useTranslation } from 'react-i18next';

// Redux
import { uiActions } from '../../../../store/slices/ui';
import { useAppDispatch, useAppSelector } from '../../../../store/store';

// Constants
import { ARTISTS_DEFAULT_IMAGE } from '../../../../constants/spotify';
import useIsMobile from '../../../../utils/isMobile';

const LoginButton = () => {
  const { t } = useTranslation(['home']);
  const dispatch = useAppDispatch();
  const tooltipOpen = useAppSelector((state) => state.ui.loginButtonOpen);

  const onClose = useCallback(() => {
    dispatch(uiActions.closeLoginButton());
  }, [dispatch]);

  // Abre NUESTRO modal de acceso. Antes se despachaba `loginToSpotify()`, que ya no redirige
  // a Spotify (es un compañero de compatibilidad que solo mira si hay token): sin sesión no
  // hacía absolutamente nada, y el botón parecía muerto.
  const onLogin = useCallback(() => {
    dispatch(uiActions.openLoginModal(ARTISTS_DEFAULT_IMAGE));
  }, [dispatch]);

  return (
    <Popconfirm
      icon={null}
      open={tooltipOpen}
      onCancel={onClose}
      onConfirm={onLogin}
      placement='bottomLeft'
      rootClassName='login-tooltip'
      cancelText={<CloseIcon />}
      title={t('You’re logged out')}
      cancelButtonProps={{ type: 'text' }}
      okButtonProps={{ className: 'white-button small' }}
      okText={t('Log In')}
      description={t('Log in to add this to your Liked Songs.')}
    >
      <WhiteButton title={t('Log In')} onClick={onLogin} />
    </Popconfirm>
  );
};

const Header = ({ opacity }: { opacity: number; title?: string }) => {
  const isMobile = useIsMobile();
  const { t } = useTranslation(['navbar']);

  const user = useAppSelector(
    (state) => state.auth.user,
    (prev, next) => prev?.id === next?.id
  );

  // `is_admin` puede no estar en el tipo del usuario: se lee de forma defensiva.
  const esAdmin = Boolean((user as unknown as { is_admin?: boolean } | null)?.is_admin);

  return (
    <div
      className={`flex r-0 w-full flex-row items-center justify-between bg-gray-900 rounded-t-md z-10`}
      style={{ backgroundColor: `rgba(12, 12, 12, ${opacity}%)` }}
    >
      <div className='flex flex-row items-center'>
        <Space>
          {/*
          <div className='news'>
            <News />
          </div> */}

          {esAdmin && (
            <Link to='/admin'>
              <Button size='small' type='text'>
                Admin
              </Button>
            </Link>
          )}

          {user ? (
            <div className='avatar-container'>
              <Link to={`/users/${user!.id}`} className='avatar-link' aria-label='Tu perfil'>
                {user?.images && user.images[0].url ? (
                  <img
                    className='avatar'
                    id='user-avatar'
                    alt='User Avatar'
                    style={{ marginTop: -1 }}
                    src={user.images[0].url}
                  />
                ) : (
                  <div className='avatar avatar-initial' style={{ marginTop: -1 }}>
                    {(user!.display_name || user!.email || '?').charAt(0).toUpperCase()}
                  </div>
                )}
              </Link>
            </div>
          ) : (
            <LoginButton />
          )}
        </Space>
      </div>
    </div>
  );
};

export default Header;
