import { FC, memo, useEffect, useState } from 'react';
import axios from '../../axios';

type Wrapped = {
  period: string;
  top_artists: { name: string; count: number }[];
  top_genres: { name: string; count: number }[];
  minutes: number;
  top_tracks: { id: string; title: string; artist: string; plays: number }[];
};

const Row = ({ title, items, render }: {
  title: string; items: unknown[]; render: (x: any) => string;
}) => (
  <div className='wrapped-card'>
    <h3 className='wrapped-card__titulo'>{title}</h3>
    {items.length ? (
      <ol className='wrapped-lista'>
        {items.map((x, i) => (
          <li key={i}>
            <span className='wrapped-lista__puesto'>{i + 1}</span>
            <span className='wrapped-lista__texto'>{render(x)}</span>
          </li>
        ))}
      </ol>
    ) : (
      <p className='wrapped-vacio'>Todavía no hay datos de este periodo.</p>
    )}
  </div>
);

/** Estadísticas (/wrapped, D5): top artistas, géneros, minutos y canciones del periodo.
 *
 *  POR QUÉ SE HA TOCADO
 *  --------------------
 *  Esta pantalla era HTML sin estilos —`<h2>`, `<button>`, `<ol>`— sobre el fondo negro de la
 *  aplicación, así que el texto salía gris oscuro sobre negro y **no se leía**: en la captura de
 *  escritorio sólo se adivinaba «0 min escuchados». No era un problema de datos: eran 56 escuchas
 *  del usuario, pero la página no se dejaba mirar. */
export const WrappedPage: FC = memo(() => {
  const [data, setData] = useState<Wrapped | null>(null);
  const [period, setPeriod] = useState<'week' | 'year'>('week');
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    setCargando(true);
    axios.get<Wrapped>('/wrapped', { params: { period } })
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setCargando(false));
  }, [period]);

  return (
    <div className='wrapped'>
      <h1 className='playlist-header'>Tus estadísticas</h1>
      <p className='playlist-subheader'>
        Lo que más has escuchado. Sólo lo ves tú.
      </p>

      <div className='wrapped-periodos'>
        {(['week', 'year'] as const).map((p) => (
          <button
            key={p}
            className={`wrapped-periodo ${period === p ? 'active' : ''}`}
            onClick={() => setPeriod(p)}
          >
            {p === 'week' ? 'Última semana' : 'Último año'}
          </button>
        ))}
      </div>

      {cargando ? (
        <p className='empty-state'>Cargando…</p>
      ) : !data ? (
        <p className='empty-state'>Sin datos de escucha todavía.</p>
      ) : (
        <>
          <p className='wrapped-minutos'>
            <b>{Math.round(data.minutes)}</b> min escuchados
          </p>

          <Row title='Artistas' items={data.top_artists} render={(x) => `${x.name} (${x.count})`} />
          <Row title='Géneros' items={data.top_genres} render={(x) => `${x.name} (${x.count})`} />
          <Row title='Canciones' items={data.top_tracks} render={(x) => `${x.title} · ${x.artist}`} />
        </>
      )}
    </div>
  );
});

export default WrappedPage;
