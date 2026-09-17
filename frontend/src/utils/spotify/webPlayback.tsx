/* eslint-disable react-hooks/exhaustive-deps */
import { useEffect, FC, memo, useCallback, useRef } from 'react';
import { message } from 'antd';
import { useAppDispatch, useAppSelector } from '../../store/store';
import { spotifyActions } from '../../store/slices/spotify';
import { playerController, AVISO } from '../../player/playerController';
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
      // Añadir aquí lo que depende de la COLA. El reproductor no puede consultarla sin crear un
      // ciclo de imports (la cola sí importa al reproductor), así que estos tres campos se
      // completan en el puente, que ve a los dos.
      //  · `context.uri`: sin él ningún selector podía saber qué playlist/álbum suena.
      //  · `shuffle` / `repeat_mode`: antes se publicaban fijos a `false`/`0` desde el
      //    reproductor, de modo que el botón de aleatorio siempre recibía `!false` (nunca se
      //    podía apagar) y el de repetir siempre mandaba "context" (nunca ciclaba).
      dispatch(
        spotifyActions.setState({
          state: {
            ...state,
            shuffle: colaController.shuffle,
            repeat_mode: colaController.repeat,
            context: colaController.uriContexto ? { uri: colaController.uriContexto } : null,
          },
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

  // Título de la pestaña: nombre de la canción mientras suena, "RadioNano" en pausa o parado.
  // Antes esto se hacía en el reductor de `setState` y sólo al cambiar de canción, de modo que
  // al pausar la pestaña seguía anunciando la canción como si siguiera sonando.
  useEffect(() => {
    const s = state as any;
    const song = s?.track_window?.current_track;
    document.title = song && s?.is_playing ? `${song.name} • ${song.artists?.[0]?.name ?? ''}` : 'RadioNano';
  }, [state]);

  // Avisos del reproductor: cuando una canción no se puede cargar (falta su archivo en el
  // servidor) se salta a la siguiente. Antes esto no se veía de ninguna manera: la reproducción
  // simplemente no arrancaba y parecía que la aplicación estaba rota.
  useEffect(() => {
    const alAvisar = (e: Event) => {
      const mensaje = (e as CustomEvent<{ mensaje?: string }>).detail?.mensaje;
      if (mensaje) message.warning({ content: mensaje, key: 'radiopv-aviso', duration: 4 });
    };
    window.addEventListener(AVISO, alAvisar);
    return () => window.removeEventListener(AVISO, alAvisar);
  }, []);

  useEffect(() => {
    playerController.bind(handleState);
    // Al terminar una canción, la cola avanza; al agotarse, entra el "Flow" (radio encadenada).
    playerController.bindEnded(() => colaController.siguiente(true));
    // Botones de la pantalla de bloqueo / auriculares del móvil.
    playerController.bindNext(() => colaController.siguiente(false));
    playerController.bindPrev(() => colaController.anterior());
    // Canción cuyo archivo no está en el servidor: saltar siempre (nunca repetirla).
    playerController.bindFallo(() => colaController.siguiente(false));
    // Volcar la cola del cliente a Redux para que el panel "Next" se pinte (B1).
    colaController.bindChange(() => dispatch(queueActions.setQueue([...colaController.cola])));
    onPlayerLoading();
    // No hay "dispositivo" de Spotify: simular el flujo para que la app continúe.
    onPlayerWaitingForDevice({ device_id: 'radiopv' });
    onPlayerDeviceSelected();
    return () => {
      playerController.bind(null as any);
      playerController.bindEnded(null);
      playerController.bindNext(null);
      playerController.bindPrev(null);
      playerController.bindFallo(null);
      colaController.bindChange(null);
    };
  }, [handleState, onPlayerLoading, onPlayerWaitingForDevice, onPlayerDeviceSelected]);

  return <>{props.children}</>;
});

export default WebPlayback;
