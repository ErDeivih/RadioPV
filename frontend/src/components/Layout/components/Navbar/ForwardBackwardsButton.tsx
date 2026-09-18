// import { useNavigate } from 'react-router-dom';

import { useTranslation } from 'react-i18next';
import { Tooltip } from '../../../Tooltip';
import { useNavigate } from 'react-router-dom';

// import { Tooltip } from '../../../Tooltip';
// import { useTranslation } from 'react-i18next';

const ForwardBackwardsButton = ({ flip }: { flip: boolean }) => {
  const navigate = useNavigate();
  const [t] = useTranslation(['navigation']);

  const navigateBack = () => {
    navigate(-1);
  };

  const navigateForward = () => {
    navigate(1);
  };

  return (
    <Tooltip title={flip ? t('Go back') : t('Go forward')}>
      <button
        // `nav-icon-button` es la clase que en el móvil garantiza 44x44 px: antes el botón medía
        // 32x32 (h-8) y es LA forma de volver atrás, así que fallar el toque era volver a fallarlo.
        className='bg-black p-2 rounded-full h-4/6 aspect-square h-8 mobile-visible nav-icon-button'
        aria-label={flip ? t('Go back') : t('Go forward')}
        onClick={flip ? navigateBack : navigateForward}
      >
        <img
          alt=''
          src={`${import.meta.env.BASE_URL}images/forward.svg`}
          className={`w-full h-full ${flip ? 'rotate-180' : ''}`}
        />
      </button>
    </Tooltip>
  );
};

export default ForwardBackwardsButton;
