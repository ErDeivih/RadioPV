/* eslint-disable no-useless-computed-key */
import { Modal } from 'antd';

import { memo, useCallback, useEffect, useState } from 'react';
import { WhiteButton } from '../Button';
import { Input, Button } from 'antd';

// Redux
import { uiActions } from '../../store/slices/ui';
import { loginWithCredentials } from '../../store/slices/auth';
import { useAppDispatch, useAppSelector } from '../../store/store';
import { register as apiRegister } from '../../api/auth';

// Constants
import { DEFAULT_PAGE_COLOR } from '../../constants/spotify';

// Utils
import tinycolor from 'tinycolor2';
import { useTranslation } from 'react-i18next';
import { getImageAnalysis2 } from '../../utils/imageAnyliser';
import useIsMobile from '../../utils/isMobile';

export const LoginModal = memo(() => {
  const dispatch = useAppDispatch();
  const [t] = useTranslation(['home']);
  const isMobile = useIsMobile();

  const [open, setOpen] = useState<boolean>(false);
  const [color, setColor] = useState<string>(DEFAULT_PAGE_COLOR);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [invite, setInvite] = useState('');
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string>('');

  const imgUrl = useAppSelector((state) => state.ui.loginModalItem);

  const onClose = useCallback(() => {
    dispatch(uiActions.closeLoginModal());
  }, [dispatch]);

  useEffect(() => {
    if (imgUrl) {
      getImageAnalysis2(imgUrl).then((color) => {
        let colorObj = tinycolor(color);
        while (colorObj.isLight()) {
          colorObj = colorObj.darken(10);
        }
        setColor(colorObj.toHexString());
        setOpen(true);
      });
    }
    return () => {
      setOpen(false);
    };
  }, [imgUrl]);

  if (!imgUrl) return null;

  const submit = async () => {
    setError('');
    try {
      if (mode === 'login') {
        await dispatch(loginWithCredentials({ email, password })).unwrap();
      } else {
        await apiRegister(email, password, displayName, invite || undefined);
        // tras registrarse, ya hay token en localStorage; pedir el usuario
        await dispatch(loginWithCredentials({ email, password })).unwrap();
      }
      onClose();
    } catch {
      setError(mode === 'login' ? 'Credenciales incorrectas' : 'No se pudo registrar');
    }
  };

  return (
    <>
      <Modal
        centered
        width={780}
        open={open}
        footer={null}
        destroyOnHidden
        onCancel={onClose}
        className='login-modal'
        wrapClassName='overlay-modal'
        style={{
          // @ts-ignore
          ['--background-color']: color,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            flexDirection: isMobile ? 'column' : 'row',
          }}
        >
          <div className='img-container'>
            <img alt='RadioNano' loading='lazy' src={imgUrl || '/icon-512.png'} />
          </div>
          <div className='content-container'>
            <h2 style={{ lineHeight: 1.4 }}>{t('Inicia sesión en RadioNano')}</h2>

            <div style={{ marginTop: 25, display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button size='small' type={mode === 'login' ? 'primary' : 'default'} onClick={() => setMode('login')}>Iniciar sesión</Button>
                <Button size='small' type={mode === 'register' ? 'primary' : 'default'} onClick={() => setMode('register')}>Registrarse</Button>
              </div>
              {mode === 'register' && (
                <Input placeholder='Nombre' value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              )}
              <Input
                placeholder='Email'
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
              />
              <Input.Password
                placeholder='Contraseña'
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onPressEnter={submit}
              />
              {mode === 'register' && (
                <Input placeholder='Código de invitación (opcional)' value={invite} onChange={(e) => setInvite(e.target.value)} />
              )}
              {error && <div style={{ color: '#e00' }}>{error}</div>}
              <WhiteButton title={mode === 'login' ? 'Iniciar sesión' : 'Crear cuenta'} onClick={submit}></WhiteButton>
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
});

LoginModal.displayName = 'LoginModal';
