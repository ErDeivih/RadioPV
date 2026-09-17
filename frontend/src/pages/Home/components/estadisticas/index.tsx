import { memo } from 'react';
import { Link } from 'react-router-dom';
import { useAppSelector } from '../../../../store/store';

const fmt = (n?: number | null) => {
  if (!n) return '0';
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return String(n);
};

/** P · "Estadísticas": popularidad por género + tops por visitas (GET /stats/popularidad). */
export const Estadisticas = memo(() => {
  const stats = useAppSelector((s) => s.home.stats);
  if (!stats) return null;
  const porGenero = (stats.por_genero ?? []).filter((g) => g.n > 0).slice(0, 10);
  const top = (stats.top_views ?? []).slice(0, 8);
  if (!porGenero.length && !top.length) return null;
  const maxMedia = Math.max(1, ...porGenero.map((g) => g.media_pop));
  return (
    <div className='home' style={{ padding: '0 20px', marginTop: 16 }}>
      <h1 className='playlist-header'>Estadísticas de popularidad</h1>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 320px', background: '#282828', borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Popularidad por género</div>
          {porGenero.map((g) => (
            <div key={g.genero} style={{ marginBottom: 6, fontSize: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', opacity: 0.85 }}>
                <span>{g.genero}</span>
                <span>{(g.media_pop * 100).toFixed(0)}%</span>
              </div>
              <div style={{ background: '#3e3e3e', borderRadius: 3, height: 5 }}>
                <div style={{ background: '#1db954', height: 5, borderRadius: 3, width: `${Math.round((g.media_pop / maxMedia) * 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
        <div style={{ flex: '1 1 320px', background: '#282828', borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Más vistas</div>
          {top.map((t) => (
            <Link key={t.track_id} to="/search" style={{ display: 'block', color: '#fff', textDecoration: 'none', marginBottom: 6, fontSize: 12 }}>
              <span style={{ fontWeight: 600 }}>{t.title}</span>
              <span style={{ opacity: 0.7 }}> — {t.artist}</span>
              <span style={{ opacity: 0.55, float: 'right' }}>{fmt(t.views)}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
});

export default Estadisticas;
