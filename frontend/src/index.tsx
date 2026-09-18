import ReactDOM from 'react-dom/client';
import { createRoot } from 'react-dom/client';
import { unstableSetRender } from 'antd';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';

import './i18n';

import TimeAgo from 'javascript-time-ago';

import en from 'javascript-time-ago/locale/en';
// Español de ESPAÑA, no de Argentina: con `es-AR` las fechas relativas salían con el formato y las
// palabras de Argentina ("hace 2 días" está bien, pero el locale arrastra otras diferencias).
import es from 'javascript-time-ago/locale/es';

TimeAgo.addDefaultLocale(en);
TimeAgo.addLocale(es);

// ── Avisos de antd (message/notification) en React 19 ────────────────────────────────────────
// Los métodos ESTÁTICOS de antd (`message.success(...)`, que es como los usa media aplicación)
// pintan su propio árbol con la API de React 18 (`ReactDOM.render`), que en React 19 ya no
// existe. Resultado real y comprobado: se guardaba el nombre de una lista, el servidor lo
// guardaba bien, y en pantalla no aparecía NINGUNA confirmación (parecía que no había hecho
// nada). Esto es exactamente lo que hace el parche oficial @ant-design/v5-patch-for-react-19,
// pero escrito aquí para no añadir otra dependencia al build.
unstableSetRender((node, container) => {
  const caja = container as Element & { _radiopvRoot?: ReturnType<typeof createRoot> };
  caja._radiopvRoot ||= createRoot(caja);
  const raiz = caja._radiopvRoot;
  raiz.render(node);
  return async () => {
    // Se espera un tick antes de desmontar: si no, React avisa de que se desmonta mientras
    // todavía se está renderizando.
    await new Promise((listo) => setTimeout(listo, 0));
    raiz.unmount();
    delete caja._radiopvRoot;
  };
});

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);
// NOTE: StrictMode is intentionally disabled. In dev it double-invokes every effect, which
// fires every Spotify API request twice and was a major contributor to hitting Spotify's
// (tightened, Feb-2026) rate limits — half the calls on the Home/Artist/Album pages were
// duplicates. Re-enable (<React.StrictMode>) if you need its checks and can tolerate 2x calls.
root.render(<App />);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();

// F1 · PWA: registrar el service worker (cachea la carcasa, nunca el audio). Solo en producción
// (en dev estorba con el HMR de Vite).
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined);
  });
}
