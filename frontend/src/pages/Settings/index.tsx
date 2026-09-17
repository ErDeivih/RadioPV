import { FC, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, ConfigProvider, Input, Select, Space, Switch, theme } from 'antd';
import { useTranslation } from 'react-i18next';

import axios from '../../axios';
import { getToken, clearToken } from '../../api/token';
import { languageActions } from '../../store/slices/language';
import { playerController } from '../../player/playerController';
import { useAppDispatch, useAppSelector } from '../../store/store';
import type { Languages } from '../../interfaces/languages';

/** Ajustes (D1): idioma, filtrar explícito (D2), editar nombre (D3), cerrar sesión y acceso a
 *  estadísticas (/wrapped). */
export const SettingsPage: FC = () => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { t } = useTranslation(['profile', 'navbar']);

  const user = useAppSelector((s) => s.auth.user);
  const language = useAppSelector((s) => s.language.language);

  const [hideExplicit, setHideExplicit] = useState(
    () => localStorage.getItem('radiopv_hide_explicit') === '1'
  );
  const [name, setName] = useState(user?.display_name ?? '');
  const [savingName, setSavingName] = useState(false);

  useEffect(() => {
    setName(user?.display_name ?? '');
  }, [user]);

  const onLanguage = (lang: Languages) => dispatch(languageActions.setLanguage({ language: lang }));

  const onToggleExplicit = (on: boolean) => {
    try { localStorage.setItem('radiopv_hide_explicit', on ? '1' : '0'); } catch { /* ignore */ }
    setHideExplicit(on);
  };

  const onSaveName = async () => {
    if (!name.trim()) return;
    setSavingName(true);
    try {
      await axios.patch('/auth/me', { display_name: name.trim() });
      // La UI lee auth.user; forzamos recargar el perfil para reflejar el nuevo nombre.
      window.location.reload();
    } catch { /* dejar que el usuario lo reintente */ }
    finally { setSavingName(false); }
  };

  const onLogout = async () => {
    try { await axios.post('/auth/logout'); } catch { /* sin sesión no pasa nada */ }
    clearToken();
    navigate('/');
    window.location.reload();
  };

  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <div style={{ maxWidth: 560, margin: '40px auto', padding: 24, color: '#fff' }}>
      <h2>{t('Settings') ?? 'Ajustes'}</h2>

      <div style={{ marginBottom: 24 }}>
        <h3>{t('Language') ?? 'Idioma'}</h3>
        <Select
          aria-label='Idioma'
          value={language}
          style={{ width: 200 }}
          onChange={onLanguage}
          options={[
            { value: 'es', label: 'Español' },
            { value: 'en', label: 'English' },
          ]}
        />
      </div>

      <div style={{ marginBottom: 24 }}>
        <h3>{t('Hide explicit content') ?? 'Ocultar contenido explícito'}</h3>
        <Switch aria-label='Ocultar contenido explícito' checked={hideExplicit} onChange={onToggleExplicit} />
      </div>

      <div style={{ marginBottom: 24 }}>
        <h3>{t('Display name') ?? 'Nombre visible'}</h3>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={user?.email}
          style={{ maxWidth: 300 }}
        />
        <Button type='primary' loading={savingName} onClick={onSaveName} style={{ marginLeft: 8 }}>
          {t('Save') ?? 'Guardar'}
        </Button>
      </div>

      <div style={{ marginBottom: 24 }}>
        <h3>{t('Sleep timer') ?? 'Temporizador de apagado'}</h3>
        <Space wrap>
          {[15, 30, 60].map((m) => (
            <Button key={m} onClick={() => playerController.setSleep(m)}>
              {m} min
            </Button>
          ))}
          <Button onClick={() => playerController.setSleep('song')}>
            {t('End of song') ?? 'Al acabar la canción'}
          </Button>
          <Button danger style={{ color: '#ff7875', borderColor: '#ff7875' }} onClick={() => playerController.cancelSleep()}>
            {t('Cancel') ?? 'Cancelar'}
          </Button>
        </Space>
      </div>

      <div style={{ marginBottom: 24 }}>
        <Button onClick={() => navigate('/wrapped')}>{t('Your statistics') ?? 'Tus estadísticas'}</Button>
      </div>

      <div>
        <Button danger style={{ color: '#ff7875', borderColor: '#ff7875' }} onClick={onLogout}>
          {t('Log out') ?? 'Cerrar sesión'}
        </Button>
      </div>
    </div>
    </ConfigProvider>
  );
};

export default SettingsPage;
