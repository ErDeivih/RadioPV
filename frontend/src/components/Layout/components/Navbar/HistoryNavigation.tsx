import { Space } from 'antd';

import NavigationButton from './NavigationButton';
import ForwardBackwardsButton from './ForwardBackwardsButton';

import { useTranslation } from 'react-i18next';
import { memo } from 'react';

/**
 * Botón de la esquina superior izquierda: el logo de la app, y lleva al código fuente.
 *
 * Antes era el logo de Spotify (FaSpotify de react-icons) y abría el GitHub del autor
 * original del proyecto en el que se basa esta interfaz. Ahora usa el logo propio de
 * RadioNano —el disco verde con la cara— y lleva al repositorio de verdad, que es el de
 * David. Ojo: el título del botón sigue siendo "Código fuente", así que lo coherente es
 * apuntar al repositorio y no al perfil.
 */
const REPOSITORIO = 'https://github.com/ErDeivih/RadioPV';

const HistoryNavigation = memo(() => {
  const { t } = useTranslation(['navbar']);
  return (
    <Space>
      <NavigationButton
        text={t('Source code')}
        onClick={() => {
          window.open(REPOSITORIO, '_blank', 'noopener,noreferrer');
        }}
        icon={
          <img
            src={`${import.meta.env.BASE_URL}icon-192.png`}
            alt='RadioNano'
            width={30}
            height={30}
            style={{ display: 'block', borderRadius: '50%' }}
          />
        }
      />

      <div className='flex flex-row items-center gap-2 h-full'>
        <ForwardBackwardsButton flip />
        <ForwardBackwardsButton flip={false} />
      </div>
    </Space>
  );
});

export default HistoryNavigation;
