import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * Barrera de errores.
 *
 * POR QUÉ HACE FALTA
 * ------------------
 * No había ninguna, y en React un error de render sin barrera desmonta TODO el árbol: la
 * pantalla se queda en blanco y en la consola sólo aparece un `TypeError`. Así se manifestó el
 * fallo de `state.spotify.state?.context.uri` (faltaba el `?.` antes de `context`): en cuanto
 * empezaba a sonar una canción, cualquier página con listas se quedaba en blanco, sin ningún
 * mensaje que dijera qué había pasado.
 *
 * Con esto el error se ve, se puede copiar, y el resto de la aplicación sigue viva.
 */
interface Props {
  children: ReactNode;
  /** Texto opcional para identificar la zona que ha fallado. */
  zona?: string;
}

interface State {
  error: Error | null;
  info: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ info: info.componentStack ?? null });
    // Queda en la consola para poder diagnosticarlo (y en los registros del navegador).
    console.error(`[RadioPV] Error de interfaz${this.props.zona ? ` en ${this.props.zona}` : ''}:`, error, info);
  }

  reintentar = () => {
    this.setState({ error: null, info: null });
  };

  render() {
    const { error, info } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        style={{
          padding: 24,
          margin: 16,
          borderRadius: 8,
          background: 'rgba(255,255,255,0.06)',
          color: '#fff',
          fontFamily: 'inherit',
        }}
        role='alert'
      >
        <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>
          Algo ha fallado en la interfaz{this.props.zona ? ` (${this.props.zona})` : ''}
        </h2>
        <p style={{ opacity: 0.8, fontSize: '0.9rem' }}>
          La música sigue sonando: el reproductor no depende de esta pantalla.
        </p>
        <pre
          style={{
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontSize: '0.8rem',
            background: 'rgba(0,0,0,0.35)',
            padding: 12,
            borderRadius: 6,
            maxHeight: 220,
            overflow: 'auto',
          }}
        >
          {error.name}: {error.message}
          {info ? `\n${info.split('\n').slice(0, 6).join('\n')}` : ''}
        </pre>
        <button
          onClick={this.reintentar}
          style={{
            marginTop: 8,
            padding: '8px 16px',
            borderRadius: 999,
            border: 'none',
            cursor: 'pointer',
            background: '#1ed760',
            color: '#000',
            fontWeight: 700,
          }}
        >
          Reintentar
        </button>
      </div>
    );
  }
}

export default ErrorBoundary;
