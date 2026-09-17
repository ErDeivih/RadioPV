import { FC } from 'react';

/** Esqueleto de carga simple y honesto (F2): se muestra mientras una pantalla pide datos,
 *  en vez de dejar la página en blanco. */
export const LoadingSkeleton: FC<{ rows?: number }> = ({ rows = 6 }) => (
  <div style={{ padding: 20, marginTop: 40 }}>
    <div
      style={{ height: 24, width: '40%', borderRadius: 6, background: '#282828', marginBottom: 24 }}
    />
    {Array.from({ length: rows }).map((_, i) => (
      <div
        key={i}
        style={{
          height: 56, borderRadius: 8, background: '#202020', marginBottom: 12,
          opacity: 1 - (i % 4) * 0.25,
        }}
      />
    ))}
  </div>
);

export default LoadingSkeleton;
