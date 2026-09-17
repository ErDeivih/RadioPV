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
import { DEFAULT_PAGE_COLOR, LOGIN_DEFAULT_IMAGE } from '../../constants/spotify';

// Utils
import tinycolor from 'tinycolor2';
import { useTranslation } from 'react-i18next';
import { getImageAnalysis2 } from '../../utils/imageAnyliser';
import useIsMobile from '../../utils/isMobile';

export const LoginModal = memo(() => {
  const dispatch = useAppDispatch();
  const [t] = useTranslation(['home']);
  const isMobile = useIsMobile();

  const [color, setColor] = useState<string>(DEFAULT_PAGE_COLOR);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [invite, setInvite] = useState('');
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string>('');

  // `loginModalOpen` manda; la imagen solo decora.
  const abierto = useAppSelector((state) => state.ui.loginModalOpen);
  const imgUrl = useAppSelector((state) => state.ui.loginModalItem);
  const imagen = imgUrl || LOGIN_DEFAULT_IMAGE;

  const onClose = useCallback(() => {
    dispatch(uiActions.closeLoginModal());
  }, [dispatch]);

  /**
   * El color de fondo se saca de la imagen, pero NO puede bloquear la apertura: antes el
   * modal solo se dibujaba dentro del `.then()` del análisis, así que si la imagen tardaba
   * o fallaba (una carátula que no carga, un CORS), el botón de "Iniciar sesión" parecía
   * muerto. Ahora el modal se abre igual y el color se aplica cuando llega; si falla, se
   * queda el color por defecto.
   */
  useEffect(() => {
    if (!abierto) {
      setColor(DEFAULT_PAGE_COLOR);
      return;
    }
    let vivo = true;
    getImageAnalysis2(imagen)
      .then((tono) => {
        if (!vivo) return;
        let colorObj = tinycolor(tono);
        while (colorObj.isLight()) colorObj = colorObj.darken(10);
        setColor(colorObj.toHexString());
      })
      .catch(() => {
        if (vivo) setColor(DEFAULT_PAGE_COLOR);
      });
    return () => {
      vivo = false;
    };
  }, [abierto, imagen]);

  if (!abierto) return null;

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
        open={abierto}
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
            <img alt='RadioNano' loading='lazy' src={imagen || '/icon-512.png'} />
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
