import {
  useCallback,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';

/**
 * Barra deslizante propia: progreso de la canción y volumen.
 *
 * POR QUÉ SE REESCRIBIÓ
 * ---------------------
 * Antes esto envolvía `react-player-controls@1.1.0` (de 2019, con peerDependencies de
 * React 15/16, sobre React 19 y cargado con `@ts-ignore`). Su `RangeControlOverlay` escucha
 * únicamente eventos de RATÓN (`mousedown` en el elemento, `mousemove`/`mouseup` en window):
 *
 *     window.addEventListener('mousemove', this.triggerRangeChange)
 *     window.addEventListener('mouseup', this.endDrag)
 *     onMouseDown: this.startDrag
 *
 * En una pantalla táctil no hay `mousemove` mientras el dedo se mueve, así que la barra de
 * progreso y la de volumen NO se podían arrastrar en el móvil: el dedo no movía nada. Aquí se
 * reimplementa con Pointer Events, que cubren ratón, dedo y lápiz por igual, con captura de
 * puntero (para que el arrastre siga funcionando aunque el dedo se salga de la barra) y con
 * `touch-action: none` para que el navegador no interprete el gesto como scroll de la página.
 *
 * Se conservan las clases CSS (`volume-sider-container`, `volume-sider`, `position-sider`,
 * `handler-sider`) para no alterar el aspecto.
 */

export type SliderDirection = 'horizontal' | 'vertical';

interface SliderProps {
  isEnabled?: boolean;
  direction?: SliderDirection;
  /** Valor normalizado 0..1. */
  value: number;
  onChange?: (value: number) => void;
  onChangeStart?: (value: number) => void;
  onChangeEnd?: (value: number) => void;
  /** Paso de las flechas del teclado (por defecto 5 %). */
  paso?: number;
  ariaLabel?: string;
  className?: string;
  style?: CSSProperties;
}

export const Slider = ({
  isEnabled = true,
  value,
  onChange,
  onChangeStart,
  onChangeEnd,
  paso = 0.05,
  ariaLabel,
  className = '',
  style,
}: SliderProps) => {
  const pista = useRef<HTMLDivElement | null>(null);
  const arrastrando = useRef(false);
  const ultimo = useRef(0);
  const [activo, setActivo] = useState(false);

  // El valor puede llegar mal (p. ej. `Math.round((duration || 0) * value)` con `duration`
  // aún sin cargar daba NaN). Sin este filtro, NaN se propagaba al estilo y la barra
  // desaparecía; además el seek acababa en NaN.
  const fraccion = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
  const pct = fraccion * 100;

  /** Posición del puntero convertida al valor 0..1 de la barra. */
  const valorEn = useCallback((clientX: number): number => {
    const el = pista.current;
    if (!el) return 0;
    const r = el.getBoundingClientRect();
    if (r.width <= 0) return 0;
    return Math.max(0, Math.min(1, (clientX - r.left) / r.width));
  }, []);

  const bajar = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isEnabled) return;
    // Imprescindible en móvil: evita que el arrastre se convierta en scroll y que el
    // navegador dispare además un emulado de ratón.
    e.preventDefault();
    const v = valorEn(e.clientX);
    ultimo.current = v;
    arrastrando.current = true;
    setActivo(true);
    // Captura del puntero: los siguientes eventos llegan a esta barra aunque el dedo se
    // salga de ella (antes el arrastre se perdía al salir del elemento).
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* no soportado */ }
    onChangeStart?.(v);
    onChange?.(v);
  };

  const mover = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isEnabled || !arrastrando.current) return;
    const v = valorEn(e.clientX);
    ultimo.current = v;
    onChange?.(v);
  };

  const soltar = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isEnabled || !arrastrando.current) return;
    arrastrando.current = false;
    setActivo(false);
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* no soportado */ }
    const v = valorEn(e.clientX);
    // Un toque sin arrastre (típico en el móvil) también debe hacer el seek en ese punto.
    ultimo.current = v;
    onChange?.(v);
    onChangeEnd?.(v);
  };

  const cancelar = () => {
    if (!arrastrando.current) return;
    arrastrando.current = false;
    setActivo(false);
    // No se llama a `onChangeEnd` con un valor inventado: se cierra con el último valor real.
    onChangeEnd?.(ultimo.current);
  };

  const teclas = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!isEnabled) return;
    let siguiente: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') siguiente = fraccion + paso;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') siguiente = fraccion - paso;
    else if (e.key === 'Home') siguiente = 0;
    else if (e.key === 'End') siguiente = 1;
    if (siguiente === null) return;
    e.preventDefault();
    const v = Math.max(0, Math.min(1, siguiente));
    ultimo.current = v;
    onChange?.(v);
    onChangeEnd?.(v);
  };

  return (
    <div className='volume-sider-container'>
      <div
        ref={pista}
        className={`volume-sider ${className}`.trim()}
        style={{ cursor: isEnabled ? 'pointer' : 'default', ...style }}
        role='slider'
        tabIndex={isEnabled ? 0 : -1}
        aria-label={ariaLabel}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        aria-disabled={!isEnabled}
        onPointerDown={bajar}
        onPointerMove={mover}
        onPointerUp={soltar}
        onPointerCancel={cancelar}
        onLostPointerCapture={cancelar}
        onKeyDown={teclas}
      >
        <div
          className='position-sider'
          style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: `${pct}%`, borderRadius: 4 }}
        />
        <div
          className={`handler-sider ${activo ? 'arrastrando' : ''}`}
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: `${pct}%`,
            marginLeft: -5,
          }}
        />
      </div>
    </div>
  );
};

export default Slider;
