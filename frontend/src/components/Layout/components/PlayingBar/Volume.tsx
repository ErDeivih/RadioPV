import { useRef, useState } from 'react';

// Components
import { Space } from 'antd';
import { Slider } from '../../../Slider';
import { Tooltip } from '../../../Tooltip';
import { VolumeIcon, VolumeMuteIcon, VolumeOneIcon, VolumeTwoIcon } from '../../../Icons';

// I18n
import { useTranslation } from 'react-i18next';
import { playerService } from '../../../../services/player';

const getIcon = (volume: number) => {
  if (volume === 0) {
    return <VolumeMuteIcon />;
  }

  if (volume < 0.4) {
    return <VolumeOneIcon />;
  }

  if (volume < 0.7) {
    return <VolumeTwoIcon />;
  }

  return <VolumeIcon />;
};

export const VolumeControls = () => {
  const { t } = useTranslation(['playingBar']);

  // El deslizador arrancaba en 1 (100%) por su cuenta y NUNCA se lo comunicaba al
  // reproductor, así que la interfaz podía marcar 100% con el audio en 0: parecía que
  // "no suena" sin motivo. Ahora arranca con el volumen real del reproductor.
  const [volume, setVolume] = useState<number>(() => playerService.getVolume());

  // Para que al quitar el silencio se recupere el volumen que había antes, no un 100%
  // fijo (que da un susto si estabas escuchando bajito).
  const anterior = useRef<number>(1);

  const muted = volume === 0;

  const aplicar = (valor: number) => {
    const acotado = Math.max(0, Math.min(1, valor));
    setVolume(acotado);
    if (acotado > 0) anterior.current = acotado;
    playerService.setVolume(Math.round(acotado * 100)).then();
  };

  // Antes esto era `setVolume(muted ? volume : 100)`: al pulsar para SILENCIAR mandaba 100
  // (o sea, nada) y dejaba el estado en 1, y al pulsar estando silenciado mandaba 0 otra
  // vez. El botón no hacía nada en ninguno de los dos sentidos.
  const alternarSilencio = () => {
    aplicar(muted ? anterior.current || 1 : 0);
  };

  return (
    <div className='volume-control-container'>
      <Space style={{ display: 'flex' }}>
        <Tooltip title={muted ? t('Unmute') : t('Mute')}>
          <div onClick={alternarSilencio} role='button' aria-label={muted ? t('Unmute') : t('Mute')}>
            {getIcon(volume)}
          </div>
        </Tooltip>

        <div className='flex items-center justify-between w-full' style={{ width: 90 }}>
          <Slider
            isEnabled
            value={volume}
            ariaLabel='Volumen'
            onChange={(value) => {
              setVolume(value);
            }}
            onChangeEnd={(value) => {
              aplicar(value);
            }}
          />
        </div>
      </Space>
    </div>
  );
};

export default VolumeControls;
