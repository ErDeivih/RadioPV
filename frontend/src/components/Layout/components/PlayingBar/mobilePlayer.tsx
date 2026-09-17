import SongDetails from './SongDetails';
import { useAppDispatch, useAppSelector } from '../../../../store/store';
import { Col, Row } from 'antd';
import { ExpandOutIcon, ListIcon, Pause, Play, SkipBack, SkipNext } from '../../../Icons';
import { Slider } from '../../../Slider';
import SongProgressBar from './SongProgressBar';
import ControlButtons from './ControlButtons';
import VolumeControls from './Volume';

// Redux
import { playerService } from '../../../../services/player';
import { useEffect, useState } from 'react';
import { getImageAnalysis2 } from '../../../../utils/imageAnyliser';
import { uiActions } from '../../../../store/slices/ui';
import tinycolor from 'tinycolor2';
import { AddSongToLibraryButton } from '../../../Actions/AddSongToLibrary';
import { spotifyActions } from '../../../../store/slices/spotify';

const PlayButton = () => {
  // `paused` es el campo que publica el reproductor. Antes no lo publicaba, así que
  // `!undefined` era `true` siempre: el botón del móvil mostraba "Pausar" y al pulsarlo
  // pausaba, pero ya no había forma de volver a darle al play desde ahí.
  const paused = useAppSelector((state) => state.spotify.state?.paused ?? true);
  return (
    <button
      aria-label={paused ? 'Reproducir' : 'Pausar'}
      onClick={() => (!paused ? playerService.pausePlayback() : playerService.startPlayback())}
    >
      {paused ? <Play /> : <Pause />}
    </button>
  );
};

/** Anterior / siguiente también en la barra del móvil: antes sólo existían en la barra de
 *  escritorio, así que desde el teléfono no se podía cambiar de canción. */
const PrevButton = () => (
  <button aria-label='Anterior' onClick={() => playerService.previousTrack()}>
    <SkipBack />
  </button>
);

const NextButton = () => (
  <button aria-label='Siguiente' onClick={() => playerService.nextTrack()}>
    <SkipNext />
  </button>
);

const QueueButton = () => {
  const dispatch = useAppDispatch();
  return (
    <button onClick={() => dispatch(uiActions.toggleQueue())}>
      <ListIcon />
    </button>
  );
};

const NowPlayingBarMobile = () => {
  const dispatch = useAppDispatch();
  const position = useAppSelector((state) => state.spotify.state?.position || 0);
  const duration = useAppSelector((state) => state.spotify.state?.duration || 1);
  const currentSong = useAppSelector(
    (state) => state.spotify.state?.track_window.current_track,
    (a, b) => a?.id === b?.id
  );
  const liked = useAppSelector((state) => state.spotify.liked);
  const [currentColor, setColor] = useState('blue');
  // Pantalla "sonando ahora" del móvil. En móvil la barra de escritorio está oculta
  // (`mobile-hidden`), así que sin esto el teléfono no tenía ni aleatorio, ni repetir, ni
  // volumen, ni una barra de progreso con tiempos.
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    if (currentSong) {
      getImageAnalysis2(currentSong.album.images[0].url).then((r) => {
        let color = tinycolor(r);
        while (color.isLight()) {
          color = color.darken(10);
        }
        setColor(color.toHexString());
      });
    }
  }, [currentSong]);

  useEffect(() => {
    document.body.style.overflow = abierto ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [abierto]);

  if (!currentSong) return <div></div>;

  const fondo = `linear-gradient(${currentColor} -50%, rgb(18, 18, 18) 300%)`;

  if (abierto) {
    return (
      <div className='mobile-now-playing' style={{ background: fondo }} role='dialog' aria-label='Sonando ahora'>
        <div className='cabecera'>
          <button aria-label='Cerrar' onClick={() => setAbierto(false)}>
            <ExpandOutIcon />
          </button>
          <span>Sonando ahora</span>
          <span style={{ width: 40 }} />
        </div>

        <img
          className='portada'
          src={currentSong.album.images[0]?.url}
          alt={currentSong.album.name}
        />

        <div className='titulo'>
          <h2>{currentSong.name}</h2>
          <p>{currentSong.artists.map((a: { name: string }) => a.name).join(', ')}</p>
        </div>

        <SongProgressBar />
        <ControlButtons />

        <div className='abajo'>
          <AddSongToLibraryButton
            size={20}
            isSaved={liked}
            id={currentSong?.id!}
            onToggle={() => dispatch(spotifyActions.setLiked({ liked: !liked }))}
          />
          <QueueButton />
          <VolumeControls />
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        className='mobile-player'
        style={{ background: fondo }}
      >
        <Row justify='space-between'>
          <Col>
            {/* Tocar la carátula/nombre abre la pantalla completa del móvil, con el resto de
                controles (progreso, aleatorio, repetir, volumen). */}
            <div
              onClick={() => setAbierto(true)}
              role='button'
              aria-label='Abrir el reproductor'
              style={{ cursor: 'pointer' }}
            >
              <SongDetails isMobile />
            </div>
          </Col>
          <Col style={{ display: 'flex' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                minWidth: 50,
                marginRight: 5,
                gap: 15,
                justifyContent: 'space-between',
              }}
            >
              <QueueButton />
              <AddSongToLibraryButton
                size={17}
                isSaved={liked}
                id={currentSong?.id!}
                onToggle={() => {
                  dispatch(spotifyActions.setLiked({ liked: !liked }));
                }}
              />
              <PrevButton />
              <PlayButton />
              <NextButton />
            </div>
          </Col>
        </Row>
        {/* Antes era una simple línea decorativa que además nunca avanzaba: leía
            `position`/`duration`, campos que el reproductor no publicaba, así que el ancho
            salía `NaN%`. Ahora es una barra de verdad: se ve avanzar y se puede tocar o
            arrastrar con el dedo para buscar dentro de la canción. */}
        <div className='time-line'>
          <Slider
            isEnabled
            value={duration > 0 ? position / duration : 0}
            ariaLabel='Progreso'
            onChangeEnd={(v) => {
              if (duration > 0) playerService.seekToPosition(Math.round(duration * v)).then();
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default NowPlayingBarMobile;
