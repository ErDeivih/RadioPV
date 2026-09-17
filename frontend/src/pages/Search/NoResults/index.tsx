import { FC, memo, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import axios from '../../../axios';
import { Button, message } from 'antd';
import { useTranslation } from 'react-i18next';

export const NoSearchResults: FC<{ searchValue: string }> = memo((props) => {
  const navigate = useNavigate();
  const [t] = useTranslation(['search']);
  const [requesting, setRequesting] = useState(false);

  const handleRequest = useCallback(async () => {
    const text = props.searchValue.trim();
    if (!text) return;
    setRequesting(true);
    try {
      await axios.post('/requests', { text });
      message.success(t('Request received') ?? 'Pedida registrada');
    } catch (e) {
      message.error((e as { response?: { status?: number } }).response?.status === 401
        ? t('Log in to request songs') ?? 'Inicia sesión para pedir canciones'
        : t('Could not send the request') ?? 'No se pudo registrar la petición');
    } finally {
      setRequesting(false);
    }
  }, [props.searchValue, t]);

  return (
    <div className='wrapper'>
      <div className='container'>
        <h3>{t('No results')}</h3>
        <p>
          {t('No results where found for')} "{props.searchValue}".
        </p>

        <Button type='primary' loading={requesting} onClick={handleRequest}>
          {t('Request this song') ?? 'Pedir esta canción'}
        </Button>

        <button onClick={() => navigate('/')}>{t('Home')}</button>
      </div>
    </div>
  );
});

NoSearchResults.displayName = 'NoSearchResults';

export default NoSearchResults;
