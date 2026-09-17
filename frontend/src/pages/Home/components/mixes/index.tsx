import { memo } from 'react';
import { Link } from 'react-router-dom';
import { useAppSelector } from '../../../../store/store';

const LABEL: Record<string, string> = {
  daily_1: 'Mix diario 1', daily_2: 'Mix diario 2', daily_3: 'Mix diario 3',
  discover: 'Descubrimiento semanal', on_repeat: 'En bucle',
  time_capsule: 'Cápsula del tiempo', radar: 'Radar de novedades',
};

/** U3 · fila "Hecho para ti": los mixes del usuario (GET /mixes) con su explicación. */
export const HechoParaTi = memo(() => {
  const mixes = useAppSelector((s) => s.home.mixes);
  if (!mixes || !mixes.length) return null;
  return (
    <div className='home' style={{ padding: '0 20px', marginTop: 16 }}>
      <h1 className='playlist-header'>Hecho para ti</h1>
      <div style={{ display: 'flex', gap: 16, overflow: 'auto' }}>
        {mixes.map((m) => (
          <Link
            key={m.kind}
            to="/search"
            style={{ minWidth: 180, maxWidth: 180, background: '#282828', borderRadius: 8, padding: 12, color: '#fff' }}
          >
            <div style={{ fontWeight: 600 }}>{LABEL[m.kind] ?? m.kind}</div>
            <div style={{ opacity: 0.7, fontSize: 12 }}>{m.explicacion}</div>
          </Link>
        ))}
      </div>
    </div>
  );
});

export default HechoParaTi;
