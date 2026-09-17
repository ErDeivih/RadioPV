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
  <div style={{ marginBottom: 24 }}>
    <h3>{title}</h3>
    {items.length ? (
      <ol>
        {items.map((x, i) => <li key={i}>{render(x)}</li>)}
      </ol>
    ) : (
      <p>—</p>
    )}
  </div>
);

/** Estadísticas (/wrapped, D5): top artistas, géneros, minutos y canciones del periodo. */
export const WrappedPage: FC = memo(() => {
  const [data, setData] = useState<Wrapped | null>(null);
  const [period, setPeriod] = useState('week');

  useEffect(() => {
    axios.get<Wrapped>('/wrapped', { params: { period } })
      .then((r) => setData(r.data))
      .catch(() => setData(null));
  }, [period]);

  return (
    <div style={{ maxWidth: 640, margin: '40px auto', padding: 24 }}>
      <h2>Estadísticas</h2>
      <div>
        {['week', 'year'].map((p) => (
          <button key={p} onClick={() => setPeriod(p)} style={{ marginRight: 8 }}>
            {p === 'week' ? 'Última semana' : 'Último año'}
          </button>
        ))}
      </div>

      {!data ? (
        <p>Sin datos de escucha todavía.</p>
      ) : (
        <>
          <p style={{ fontSize: 32 }}>{Math.round(data.minutes)} min escuchados</p>
          <Row title="Artistas" items={data.top_artists} render={(x) => `${x.name} (${x.count})`} />
          <Row title="Géneros" items={data.top_genres} render={(x) => `${x.name} (${x.count})`} />
          <Row title="Canciones" items={data.top_tracks} render={(x) => `${x.title} · ${x.artist}`} />
        </>
      )}
    </div>
  );
});

export default WrappedPage;
