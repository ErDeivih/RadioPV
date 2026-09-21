import { FC, RefObject, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Divider } from 'antd';

import axios from '../../axios';
import { toTrack, urlDeApi } from '../../api/adapt';
import type { TrackOut } from '../../api/types';
import { Portada } from '../../components/Lists/GridCards';
import { PlayCircle } from '../../components/Lists/PlayCircle';
import SongView, { SongViewComponents } from '../../components/SongsTable/songView';
import TableHeader, { TableHeaderComponents } from '../../components/SongsTable/header';
import { userService } from '../../services/users';
import { homeActions } from '../../store/slices/home';
import { useAppDispatch, useAppSelector } from '../../store/store';

import type { Track } from '../../interfaces/track';

/** Nombre en castellano de cada tipo de mix (el `kind` lo pone la API). */
const LABEL: Record<string, string> = {
  daily_1: 'Mix diario 1',
  daily_2: 'Mix diario 2',
  daily_3: 'Mix diario 3',
  discover: 'Descubrimiento semanal',
  on_repeat: 'En bucle',
  time_capsule: 'Cápsula del tiempo',
  radar: 'Radar de novedades',
};

/** Página de un mix de «Hecho para ti» (`/mix/:kind`).
 *
 *  POR QUÉ EXISTE
 *  --------------
 *  Las tarjetas de «Hecho para ti» llevaban a `/search`, que no busca nada: la música de la portada
 *  no se podía ni ver ni escuchar. Las canciones de cada mix ya estaban guardadas en la base
 *  (`tracks_json`), pero no había ni ruta que las sirviera ni pantalla donde verlas. */
const MixPage: FC<{ container: RefObject<HTMLDivElement | null> }> = (props) => {
  const dispatch = useAppDispatch();
  const { kind } = useParams<{ kind: string }>();

  const mixes = useAppSelector((state) => state.home.mixes);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [liked, setLiked] = useState<Record<string, boolean>>({});
  const [cargando, setCargando] = useState(true);

  const mix = useMemo(() => mixes.find((m) => m.kind === kind), [mixes, kind]);

  // Al entrar directo por la URL (o al recargar) la portada no ha cargado los mixes todavía: sin
  // esto la cabecera se quedaba sin nombre y sin explicación.
  useEffect(() => {
    if (!mixes.length) dispatch(homeActions.fetchMixes());
  }, [dispatch, mixes.length]);

  useEffect(() => {
    if (!kind) return;
    let vivo = true;
    setCargando(true);
    axios
      .get<TrackOut[]>(`/mixes/${kind}/tracks`)
      .then(async ({ data }) => {
        if (!vivo) return;
        const lista = data.map(toTrack);
        setTracks(lista);
        // Los corazones se pintan con lo que el usuario ya tenía en «Me gusta», no con un corazón
        // vacío a fuego: si no, la lista mentiría sobre lo que hay guardado.
        const { data: guardadas } = await userService
          .checkSavedTracks(data.map((t) => String(t.id)))
          .catch(() => ({ data: [] as boolean[] }));
        if (!vivo) return;
        setLiked(
          Object.fromEntries(data.map((t, i) => [String(t.id), !!guardadas[i]]))
        );
      })
      .catch(() => {
        if (vivo) setTracks([]);
      })
      .finally(() => {
        if (vivo) setCargando(false);
      });
    return () => {
      vivo = false;
    };
  }, [kind]);

  const toggleLike = useCallback((id: string) => {
    setLiked((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const titulo = kind ? (LABEL[kind] ?? mix?.kind ?? kind) : '';

  const uriDelMix = `radiopv:mix:${kind}`;
  // Para que el botón grande se ponga en «pausa» sólo si lo que suena es ESTE mix.
  const esElActual = useAppSelector((state) => state.spotify.state?.context?.uri === uriDelMix);

  // Las rutas de la API hay que hacerlas absolutas (ver `urlDeApi`): en crudo, nginx devuelve el
  // HTML de la aplicación y las carátulas salen rotas.
  const caratulas = useMemo(
    () => (mix?.collage ?? []).map((url) => urlDeApi(url)).filter((url): url is string => !!url),
    [mix]
  );

  return (
    <div className='Playlist-section' ref={props.container}>
      <div className='mix-cabecera'>
        <div className='mix-cabecera__portada'>
          {caratulas.length ? (
            <Portada images={caratulas} title={titulo} />
          ) : (
            <div className='mix-card__fondo'>{titulo}</div>
          )}
        </div>

        <div className='mix-cabecera__datos'>
          <Link to='/' className='mix-cabecera__tipo'>
            Hecho para ti
          </Link>
          <h1 className='mix-cabecera__titulo'>{titulo}</h1>
          {mix?.explicacion ? <p className='mix-cabecera__texto'>{mix.explicacion}</p> : null}
          <p className='mix-cabecera__texto'>
            {tracks.length} canciones{mix ? ` · ${mix.n_tracks} en la mezcla` : ''}
          </p>
        </div>
      </div>

      <div className='playlist-list'>
        <div className='mix-controles'>
          <PlayCircle
            size={30}
            big
            image={caratulas[0]}
            isCurrent={esElActual}
            context={{ context_uri: uriDelMix }}
          />
        </div>

        {tracks.length ? (
          <div className='playlist-table'>
            <TableHeader
              view='LIST'
              fields={[
                TableHeaderComponents.Index,
                TableHeaderComponents.Title,
                TableHeaderComponents.Album,
                TableHeaderComponents.Space,
                TableHeaderComponents.Time,
                TableHeaderComponents.Space,
              ]}
            />
          </div>
        ) : (
          <Divider />
        )}

        {cargando && !tracks.length ? <p className='mix-cabecera__texto'>Cargando…</p> : null}

        {!cargando && !tracks.length ? (
          <p className='mix-cabecera__texto'>
            Este mix todavía no tiene canciones. Vuelve a la portada y prueba de nuevo en un rato.
          </p>
        ) : null}

        <div style={{ paddingBottom: 30 }}>
          {tracks.map((song, index) => (
            <SongView
              key={song.id}
              activable
              view='LIST'
              index={index}
              song={song}
              saved={liked[song.id]}
              onToggleLike={() => toggleLike(song.id)}
              context={{ context_uri: uriDelMix, offset: { position: index } }}
              fields={[
                SongViewComponents.TitleWithCover,
                SongViewComponents.Artists,
                SongViewComponents.Album,
                (props) => <SongViewComponents.AddToLiked {...props} onLikeRefresh={toggleLike} />,
                SongViewComponents.Time,
                SongViewComponents.Actions,
              ]}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

MixPage.displayName = 'MixPage';

export default MixPage;
