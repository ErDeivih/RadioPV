import { memo } from 'react';
import { WhiteButton } from '../../../Button';
import { useTranslation } from 'react-i18next';
import { useAppDispatch } from '../../../../store/store';
import { uiActions } from '../../../../store/slices/ui';
import { LOGIN_DEFAULT_IMAGE } from '../../../../constants/spotify';
import useIsMobile from '../../../../utils/isMobile';

export const LoginFooter = memo(() => {
  const isMobile = useIsMobile();
  const [t] = useTranslation(['home']);
  const dispatch = useAppDispatch();

  if (isMobile) return null;

  // Abre NUESTRO modal de acceso. Antes iba a `loginToSpotify()`, que ya no redirige a
  // Spotify: sin sesión no hacía nada y el botón parecía roto.
  const onLogin = () => dispatch(uiActions.openLoginModal(LOGIN_DEFAULT_IMAGE));

  return (
    <div className='login-footer' style={{ margin: '0px 10px' }}>
      <div className='login-container'>
        <div>
          <p className='title'>{t('Preview')}</p>
          <p className='description'>{t('Log In to access all the features of the app')}.</p>
        </div>

        <WhiteButton title={t('Log In')} onClick={onLogin} />
      </div>
    </div>
  );
});
