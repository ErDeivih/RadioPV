import { FC, memo, useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Checkbox, Input } from 'antd';

import axios from '../../axios';

type Falta = { title: string; artist: string };

type Resultado = {
  playlist: { id: number; name: string; n_tracks: number };
  nombre: string;
  total: number;
  encontradas: number;
  faltan: Falta[];
  pedidas: number;
  aviso: string | null;
};

/** Importar una lista de Spotify (`/importar`).
 *
 *  Lo pidió el usuario: «me gustaría una opción en donde pasara un playlist de spotify y se me creara
 *  igual en mi aplicación». Se pega el enlace, el servidor lee la lista pública y busca sus canciones
 *  EN LA BIBLIOTECA (no baja nada de Spotify): las que están entran en una lista nueva, y las que no
 *  se dicen y se pueden pedir al recolector para que las baje.
 *
 *  Se enseña SIEMPRE el recuento («de 50, 23»): crear la lista y callar que entró la mitad sería
 *  justo lo que no se quiere, una lista que parece completa y no lo está. */
const ImportarSpotify: FC = memo(() => {
  const [url, setUrl] = useState('');
  const [pedir, setPedir] = useState(true);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');
  const [res, setRes] = useState<Resultado | null>(null);

  const importar = useCallback(async () => {
    const enlace = url.trim();
    if (!enlace) {
      setError('Pega el enlace de una lista de Spotify.');
      return;
    }
    setCargando(true);
    setError('');
    setRes(null);
    try {
      const { data } = await axios.post<Resultado>('/importar/spotify', { url: enlace, pedir });
      setRes(data);
    } catch (e) {
      const detalle = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setError(detalle || 'No se ha podido importar la lista.');
    } finally {
      setCargando(false);
    }
  }, [url, pedir]);

  return (
    <div className='importar'>
      <h1 className='playlist-header'>Importar una lista de Spotify</h1>
      <p className='playlist-subheader'>
        Pega el enlace de una lista <b>pública</b> y se crea aquí con la música que ya tengas. No se
        baja nada de Spotify: se buscan las canciones en tu biblioteca.
      </p>

      <div className='importar-caja'>
        <Input
          size='large'
          allowClear
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onPressEnter={importar}
          placeholder='https://open.spotify.com/playlist/…'
          disabled={cargando}
        />

        <Checkbox checked={pedir} onChange={(e) => setPedir(e.target.checked)} disabled={cargando}>
          Pedir las que no tenga (las busca el recolector)
        </Checkbox>

        <Button type='primary' size='large' loading={cargando} onClick={importar}>
          Importar
        </Button>
      </div>

      {error ? (
        <Alert style={{ marginTop: 16 }} type='error' showIcon message={error} />
      ) : null}

      {res ? (
        <div className='importar-resultado'>
          <Alert
            type={res.encontradas ? 'success' : 'warning'}
            showIcon
            message={`«${res.nombre}»: ${res.encontradas} de ${res.total} canciones`}
            description={
              <>
                <div>
                  Ya está en <Link to={`/playlist/${res.playlist.id}`}>tu lista «{res.nombre}»</Link>.
                </div>
                {res.pedidas ? (
                  <div>
                    {res.pedidas} {res.pedidas === 1 ? 'canción pedida' : 'canciones pedidas'} al
                    recolector: aparecerán en la lista cuando se descarguen.
                  </div>
                ) : null}
                {res.aviso ? <div>{res.aviso}</div> : null}
              </>
            }
          />

          {res.faltan.length ? (
            <div className='importar-faltan'>
              <h3>No están en la biblioteca ({res.faltan.length})</h3>
              <ul>
                {res.faltan.slice(0, 40).map((f, i) => (
                  <li key={`${f.title}-${i}`}>
                    {f.title}
                    {f.artist ? <span className='importar-artista'> · {f.artist}</span> : null}
                  </li>
                ))}
              </ul>
              {res.faltan.length > 40 ? (
                <p className='importar-artista'>…y {res.faltan.length - 40} más.</p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
});

export default ImportarSpotify;
