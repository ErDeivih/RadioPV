/* eslint-disable react-hooks/exhaustive-deps */
import { useEffect, FC, memo, useCallback, useRef } from 'react';
import { useAppDispatch, useAppSelector } from '../../store/store';
import { spotifyActions } from '../../store/slices/spotify';
import { playerController } from '../../player/playerController';
import { colaController } from '../../player/queueController';
import { playerService } from '../../services/player';
import { userService } from '../../services/users';
import { queueActions } from '../../store/slices/queue';

export interface WebPlaybackProps {
  onPlayerError: (message: string) => void;
  onPlayerRequestAccessToken: () => Promise<string>;
  onPlayerLoading: () => void;
  onPlayerWaitingForDevice: (data: any) => void;
  onPlayerDeviceSelected: () => void;
  playerName: string;
  playerInitialVolume: number;
  playerRefreshRateMs?: number;
  playerAutoConnect?: boolean;
  children?: any;
}

/** Reproductor de RadioPV: usa nuestro <audio> (playerController), NO el SDK de Spotify Connect.
 *  Mantiene la interfaz WebPlaybackProps para que App.tsx no cambie. */
const WebPlayback: FC<WebPlaybackProps> = memo((props) => {
  const dispatch = useAppDispatch();
  const { onPlayerLoading, onPlayerWaitingForDevice, onPlayerDeviceSelected } = props;

  // Estado que leen los atajos de teclado (B7).
  const state = useAppSelector((s) => s.spotify.state);
  const liked = useAppSelector((s) => s.spotify.liked);
  const mutedRef = useRef(false);

  const handleState = useCallback((state: any | null) => {
    if (state) {
      // Reflejar shuffle/repeat reales en el estado que consume la UI (los botones).
      dispatch(
        spotifyActions.setState({
          state: { ...state, shuffle: colaController.shuffle, repeat_mode: colaController.repeat },
        })
      );
    }
  }, [dispatch]);

  // Atajos de teclado (B7): espacio = play/pausa · flechas = ±10 s · M = silencio · L = me gusta.
  useEffect(() => {
    const s = state as any;   // el estado emitido incluye is_playing/position_ms (no el tipo SDK)
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag && ['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;

      if (e.code === 'Space') {
        e.preventDefault();
        if (s?.is_playing === false) void playerService.startPlayback();
        else void playerService.pausePlayback();
        return;
      }
      if (e.code === 'ArrowRight' || e.code === 'ArrowLeft') {
        e.preventDefault();
        const dir = e.code === 'ArrowRight' ? 1 : -1;
        const pos = (s?.position_ms ?? 0) + dir * 10000;
        const max = s?.duration_ms ?? pos;
        void playerService.seekToPosition(Math.max(0, Math.min(pos, max)));
        return;
      }
      if (e.key === 'm' || e.key === 'M') {
        mutedRef.current = !mutedRef.current;
        playerService.setVolume(mutedRef.current ? 0 : 100);
        return;
      }
      if (e.key === 'l' || e.key === 'L') {
        const id = s?.track_window?.current_track?.id;
        if (!id) return;
        void (liked ? userService.deleteTracks([id]) : userService.saveTracks([id]));
        return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [state, liked]);

  useEffect(() => {
    playerController.bind(handleState);
    // Al terminar una canción, la cola avanza; al agotarse, entra el "Flow" (radio encadenada).
    playerController.bindEnded(() => colaController.siguiente(true));
    // Volcar la cola del cliente a Redux para que el panel "Next" se pinte (B1).
    colaController.bindChange(() => dispatch(queueActions.setQueue([...colaController.cola])));
    onPlayerLoading();
    // No hay "dispositivo" de Spotify: simular el flujo para que la app continúe.
    onPlayerWaitingForDevice({ device_id: 'radiopv' });
    onPlayerDeviceSelected();
    return () => {
      playerController.bind(null as any);
      playerController.bindEnded(null);
      colaController.bindChange(null);
    };
  }, [handleState, onPlayerLoading, onPlayerWaitingForDevice, onPlayerDeviceSelected]);

  return <>{props.children}</>;
});

export default WebPlayback;
