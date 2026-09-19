// Components
import { Col, Modal, Row } from 'antd';
import { useCallback, useState } from 'react';
import VolumeControls from './Volume';
import { Tooltip } from '../../../Tooltip';
import { FullScreenPlayer } from '../../../FullScreen';
import { FullScreen, useFullScreenHandle } from 'react-full-screen';

// Services
import { getLyrics, type Letra } from '../../../../api/lyrics';

// Icons
import {
  DetailsIcon,
  DeviceIcon,
  ExpandIcon,
  ListIcon,
  MicrophoneIcon,
  PhoneIcon,
} from '../../../Icons';

// I18n
import { useTranslation } from 'react-i18next';

// Redux
import { uiActions } from '../../../../store/slices/ui';
import { useAppDispatch, useAppSelector } from '../../../../store/store';

/**
 * Botón de «Letra».
 *
 * Antes este botón abría… el **selector de idioma** (`openLanguageModal`). Prometía la letra y
 * hacía otra cosa: el mismo tipo de fallo que el «elegir foto» de las listas. Ahora pide la letra
 * al servidor y la enseña; si no la hay, lo dice, que es lo que pasa con buena parte del catálogo
 * (remixes, sesiones, música poco conocida).
 */
const LyricsButton = () => {
  const { t } = useTranslation(['playingBar']);
  const [abierto, setAbierto] = useState(false);
  const [cargando, setCargando] = useState(false);
  const [letra, setLetra] = useState<Letra | null>(null);

  const track = useAppSelector((state) => state.spotify.state?.track_window.current_track);
  const trackId = track?.id;

  const abrir = useCallback(() => {
    if (!trackId) return;
    setAbierto(true);
    setLetra(null);
    setCargando(true);
    getLyrics(String(trackId))
      .then(setLetra)
      .catch(() => setLetra({ letra: null, encontrada: false }))
      .finally(() => setCargando(false));
  }, [trackId]);

  return (
    <>
      <Tooltip title={trackId ? t('Lyrics') : ''}>
        <button
          style={{ marginLeft: 5, marginRight: 5 }}
          aria-label='Letra'
          disabled={!trackId}
          onClick={abrir}
        >
          <MicrophoneIcon />
        </button>
      </Tooltip>

      <Modal
        open={abierto}
        onCancel={() => setAbierto(false)}
        footer={null}
        centered
        width={520}
        title={
          <div style={{ lineHeight: 1.3 }}>
            <div style={{ fontWeight: 700 }}>{track?.name}</div>
            <div style={{ fontSize: '0.8rem', color: '#b3b3b3' }}>
              {track?.artists?.map((a) => a.name).join(', ')}
            </div>
          </div>
        }
      >
        {cargando ? (
          <div className='lyrics-cargando'>Buscando la letra…</div>
        ) : letra?.encontrada ? (
          // `white-space: pre-line` respeta los saltos de línea que trae la letra.
          <div className='lyrics-texto'>{letra.letra}</div>
        ) : (
          <div className='lyrics-vacio'>
            No hay letra para esta canción.
            <br />
            <small style={{ color: '#b3b3b3' }}>
              Es normal en remixes, sesiones de DJ y música poco conocida.
            </small>
          </div>
        )}
      </Modal>
    </>
  );
};

const DetailsButton = () => {
  const dispatch = useAppDispatch();
  const { t } = useTranslation(['playingBar']);

  const active = useAppSelector((state) => !state.ui.detailsCollapsed);

  return (
    <>
      <Tooltip title={t('Now playing view')}>
        <button
          aria-label='Vista de reproducción'
          className={active ? 'active-icon-button tablet-hidden' : 'tablet-hidden'}
          onClick={() => dispatch(uiActions.toggleDetails())}
          style={{
            marginLeft: 5,
            marginRight: 10,
            cursor: 'pointer',
          }}
        >
          <DetailsIcon active={active} />
        </button>
      </Tooltip>
    </>
  );
};

const QueueButton = () => {
  const dispatch = useAppDispatch();
  const { t } = useTranslation(['playingBar']);
  const queueCollapsed = useAppSelector((state) => state.ui.queueCollapsed);
  return (
    <Tooltip title={t('Queue')}>
      <button
        aria-label='Cola'
        onClick={() => dispatch(uiActions.toggleQueue())}
        className={!queueCollapsed ? 'active-icon-button' : ''}
        style={{
          marginLeft: 10,
          marginRight: 5,
          cursor: queueCollapsed ? 'pointer' : 'not-allowed',
        }}
      >
        <ListIcon active={!queueCollapsed} />
      </button>
    </Tooltip>
  );
};

const ExpandButton = () => {
  const { t } = useTranslation(['playingBar']);

  const handle = useFullScreenHandle();
  const isQueueOpen = useAppSelector((state) => !state.ui.queueCollapsed);

  return (
    <>
      <FullScreen handle={handle}>
        <FullScreenPlayer onExit={handle.exit} />
      </FullScreen>

      <Tooltip title={t('Full Screen')}>
        <button
          aria-label='Pantalla completa'
          className='tablet-hidden'
          onClick={handle.enter}
          style={{
            marginRight: 5,
            cursor: isQueueOpen ? 'pointer' : 'not-allowed',
          }}
        >
          <ExpandIcon />
        </button>
      </Tooltip>
    </>
  );
};

const DeviceButton = () => {
  const dispatch = useAppDispatch();
  const { t } = useTranslation(['playingBar']);
  const isDeviceOpen = useAppSelector((state) => !state.ui.devicesCollapsed);

  const currentDevice = useAppSelector((state) => state.spotify.activeDeviceType);

  return (
    <Tooltip title={t('Connect to a device')}>
      <button
        aria-label='Conectar dispositivo'
        onClick={() => dispatch(uiActions.toggleDevices())}
        className={isDeviceOpen ? 'active-icon-button' : ''}
        style={{ marginTop: 4, cursor: isDeviceOpen ? 'pointer' : 'not-allowed' }}
      >
        {currentDevice === 'Smartphone' ? (
          <PhoneIcon active={isDeviceOpen} />
        ) : (
          <DeviceIcon active={isDeviceOpen} />
        )}
      </button>
    </Tooltip>
  );
};

const ExtraControlButtons = () => {
  return (
    <div>
      <Row gutter={18} align='middle'>
        <DetailsButton />

        <LyricsButton />

        <QueueButton />

        <Col className='hiddable-icon'>
          <DeviceButton />
        </Col>

        <Col>
          <VolumeControls />
        </Col>

        <Col>
          <ExpandButton />
        </Col>
      </Row>
    </div>
  );
};

export default ExtraControlButtons;
