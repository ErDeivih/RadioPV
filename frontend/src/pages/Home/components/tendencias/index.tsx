import { memo } from 'react';
import { Link } from 'react-router-dom';
import { useAppSelector } from '../../../../store/store';
import type { PopularidadItem } from '../../../../store/slices/home';

const fmt = (n?: number | null) => {
  if (!n) return '0';
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return String(n);
};

const badge = (t: PopularidadItem) => {
  if (t.variacion) return `▲ ${Math.round(t.variacion * 100)}%`;
  return 'Nuevo';
};

/** P · fila "Tendencias": subiendo recientemente o recién populares, por visitas de YouTube.
 *  Se refresca con el worker cada 6h (GET /stats/popularidad). */
export const Tendencias = memo(() => {
  const p = useAppSelector((s) => s.home.popularidad);
  const items = [...(p?.subiendo ?? []), ...(p?.nuevas ?? [])].slice(0, 12);
  if (!items.length) return null;
  return (
    <div className='home' style={{ padding: '0 20px', marginTop: 16 }}>
      <h1 className='playlist-header'>Tendencias</h1>
      <div style={{ display: 'flex', gap: 16, overflow: 'auto' }}>
        {items.map((t) => (
          <Link
            key={t.track_id}
            to="/search"
            style={{ minWidth: 180, maxWidth: 180, background: '#282828', borderRadius: 8, padding: 12, color: '#fff' }}
          >
            <div style={{ fontWeight: 600 }}>{t.title}</div>
            <div style={{ opacity: 0.7, fontSize: 12 }}>{t.artist}</div>
            <div style={{ opacity: 0.6, fontSize: 11, marginTop: 4 }}>
              {badge(t)} · {fmt(t.views)}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
});

export default Tendencias;
