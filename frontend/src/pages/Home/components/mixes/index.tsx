import { memo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Portada } from '../../../../components/Lists/GridCards';
import { PlayCircle } from '../../../../components/Lists/PlayCircle';
import { useAppSelector } from '../../../../store/store';
import type { MixResumen } from '../../../../store/slices/home';

/** Nombre de cada mix. El `kind` es lo que manda la API; esto sólo lo pone en castellano. */
const LABEL: Record<string, string> = {
  daily_1: 'Mix diario 1',
  daily_2: 'Mix diario 2',
  daily_3: 'Mix diario 3',
  discover: 'Descubrimiento semanal',
  on_repeat: 'En bucle',
  time_capsule: 'Cápsula del tiempo',
  radar: 'Radar de novedades',
};

const MixCard = memo(({ mix }: { mix: MixResumen }) => {
  const navigate = useNavigate();
  const { t } = useTranslation(['playlist']);

  const paused = useAppSelector((state) => state.spotify.state?.paused);
  const contextUri = useAppSelector((state) => state.spotify.state?.context?.uri);
  const isCurrent = contextUri === mix.uri;

  const label = LABEL[mix.kind] ?? mix.kind;

  const abrir = useCallback(() => navigate(`/mix/${mix.kind}`), [navigate, mix.kind]);

  return (
    <div
      className='mix-card'
      role='button'
      tabIndex={0}
      aria-label={label}
      onClick={abrir}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') abrir();
      }}
    >
      <div className='mix-card__portada'>
        {mix.collage.length ? (
          <Portada images={mix.collage} title={label} />
        ) : (
          // Sin ninguna carátula local no se pinta un `img` roto: se pinta un fondo con el nombre
          // del mix, que al menos se ve entero y no parece que falte un fichero.
          <div className='mix-card__fondo'>{label}</div>
        )}

        {/* El botón de reproducir NO navega: para eso ya está la tarjeta entera (y en el móvil,
         *  sin ratón, abrir y sonar tienen que ser dos cosas distintas). `PlayCircle` corta la
         *  propagación del clic, así que pulsar aquí suena el mix sin salir de la portada. */}
        <div className={`circle-play-div ${isCurrent && !paused ? 'active' : ''}`}>
          <PlayCircle
            image={mix.collage[0]}
            isCurrent={isCurrent}
            context={{ context_uri: mix.uri }}
          />
        </div>
      </div>

      <h3 className='mix-card__titulo'>{label}</h3>
      {mix.explicacion ? <p className='mix-card__explicacion'>{mix.explicacion}</p> : null}
      <span className='mix-card__n'>
        {mix.n_tracks} {t(mix.n_tracks === 1 ? 'song' : 'songs')}
      </span>
    </div>
  );
});

MixCard.displayName = 'MixCard';

/** U3 · fila "Hecho para ti": los mixes del usuario (GET /mixes).
 *
 *  Antes eran cuadros de texto grises que llevaban a `/search`: no tenían imagen, no decían cuántas
 *  canciones traían y al pulsarlos no sonaba nada. Ahora cada tarjeta lleva el mosaico de sus
 *  carátulas, su botón de reproducir (la URI la manda el servidor, `radiopv:mix:<kind>`) y abre la
 *  página del mix, que enseña su lista de canciones. */
export const HechoParaTi = memo(() => {
  const mixes = useAppSelector((s) => s.home.mixes);

  if (!mixes || !mixes.length) return null;

  return (
    <div className='home hecho-para-ti'>
      <h1 className='playlist-header'>Hecho para ti</h1>
      <div className='hecho-para-ti__fila'>
        {mixes.map((m) => (
          <MixCard key={m.kind} mix={m} />
        ))}
      </div>
    </div>
  );
});

HechoParaTi.displayName = 'HechoParaTi';

export default HechoParaTi;
