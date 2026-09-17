/* eslint-disable react-hooks/exhaustive-deps */
// Components
import { Slider } from '../../../Slider';

// Utils
import { msToTime } from '../../../../utils';

// Redux
import { useAppSelector } from '../../../../store/store';
import { playerService } from '../../../../services/player';
import { memo, useEffect, useState } from 'react';

/** Barra de progreso: arrastrable con el ratón Y con el dedo, y también con el teclado.
 *
 *  Antes leía `state.spotify.state?.position` y `?.duration`, campos que el reproductor NO
 *  publicaba (mandaba `position_ms`/`duration_ms`), así que el valor era siempre `undefined`:
 *  los tiempos se quedaban en 0:00, la barra no avanzaba y al arrastrarla el seek calculaba
 *  `Math.round((duration || 0) * value)` = 0, o sea que saltaba al principio de la canción.
 *  Ahora el reproductor sí publica `position`/`duration` en milisegundos. */
const SongProgressBar = memo(() => {
  const hasState = useAppSelector((state) => !!state.spotify.state);
  const position = useAppSelector((state) => state.spotify.state?.position ?? 0);
  const duration = useAppSelector((state) => state.spotify.state?.duration ?? 0);

  const [value, setValue] = useState<number>(0);
  const [selecting, setSelecting] = useState<boolean>(false);

  useEffect(() => {
    // Mientras el usuario arrastra no se pisa su posición con la del reproductor.
    if (selecting) return;
    if (!Number.isFinite(position) || !Number.isFinite(duration) || duration <= 0) {
      setValue(0);
      return;
    }
    setValue(Math.max(0, Math.min(1, position / duration)));
  }, [position, duration, selecting]);

  // Al soltar: sólo se hace seek si de verdad hay una canción cargada y una duración conocida.
  // Antes se hacía `if (!loaded) return;` dejando el deslizador desplazado y sin efecto.
  const buscar = (valor: number) => {
    setSelecting(false);
    if (!Number.isFinite(valor)) return;
    if (!hasState || !Number.isFinite(duration) || duration <= 0) {
      setValue(0);
      return;
    }
    setValue(valor);
    playerService.seekToPosition(Math.round(duration * valor)).then();
  };

  const mostrado = selecting ? Math.round(duration * value) : position;

  return (
    <div className='flex items-center justify-between w-full'>
      <div className='text-white mr-2 text-xs'>{mostrado > 0 ? msToTime(mostrado) : '0:00'}</div>
      <div style={{ width: '100%' }}>
        <Slider
          isEnabled
          value={value}
          ariaLabel='Barra de progreso'
          onChangeStart={() => {
            setSelecting(true);
          }}
          onChange={(v) => {
            setValue(v);
          }}
          onChangeEnd={buscar}
        />
      </div>
      <div className='text-white ml-2 text-xs'>
        {duration > 0 ? msToTime(duration) : '0:00'}
      </div>
    </div>
  );
});

export default SongProgressBar;
