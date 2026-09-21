import { FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  List,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';

// Services
import {
  borrarPeticion,
  buscarParaPedir,
  crearPeticion,
  duracionLegible,
  misPeticiones,
  type BusquedaParaPedir,
  type Peticion,
} from '../../services/peticiones';

// Redux
import { useAppSelector } from '../../store/store';
import { playerService } from '../../services/player';

const { Title, Paragraph, Text } = Typography;

const ESTADOS: Record<string, { color: string; texto: string; ayuda: string }> = {
  pendiente: {
    color: 'processing',
    texto: 'En cola',
    ayuda: 'El recolector la buscará en la próxima vuelta (cada 15 minutos).',
  },
  descargada: {
    color: 'success',
    texto: 'Descargada',
    ayuda: 'Ya está en la biblioteca: búscala o escúchala desde aquí.',
  },
  fallida: {
    color: 'error',
    texto: 'No encontrada',
    ayuda: 'Se buscó en las tiendas de música y en YouTube y no apareció. Prueba con otro nombre.',
  },
};

/**
 * Página para pedir una canción que no esté en la biblioteca.
 *
 * POR QUÉ ASÍ
 * -----------
 * Primero era una caja de texto a ciegas: escribías y a esperar. Tres problemas de eso, y los tres
 * se resuelven con la búsqueda:
 *
 *  1. **No sabías si ya la tenías.** Pedir algo que ya está es trabajo perdido para el recolector
 *     (y el usuario se queda esperando algo que podía oír en el momento).
 *  2. **No sabías cuál de las versiones se iba a bajar.** De un tema hay el original, el remix, el
 *     directo y veinte subidas distintas; el buscador por texto bajaba la que le parecía, y muchas
 *     veces no era la que se quería. Ahora se ven los resultados REALES de YouTube con su duración
 *     y se elige uno.
 *  3. **No sabías si se podía.** Ahora se ve si está en casa, si hay algo en YouTube o si ya está
 *     pedido, antes de pedir nada.
 *
 * Sigue sirviendo para lo que más se pide —mashups, remixes y sesiones de DJ—, que no están en las
 * tiendas de música y sólo se encuentran en YouTube.
 */
export const PedirCanciones: FC = () => {
  const user = useAppSelector((state) => state.auth.user);

  const [texto, setTexto] = useState('');
  const [buscando, setBuscando] = useState(false);
  const [resultado, setResultado] = useState<BusquedaParaPedir | null>(null);
  const [enviando, setEnviando] = useState<string | null>(null); // «cualquiera» o el id del vídeo
  const [peticiones, setPeticiones] = useState<Peticion[]>([]);
  const [cargando, setCargando] = useState(true);

  // Cada búsqueda lleva un número: si el usuario escribe deprisa, sólo vale la ÚLTIMA respuesta.
  // Sin esto, una búsqueda lenta («Bad») podía llegar después de una rápida («Bad Bunny») y dejar
  // en pantalla los resultados de la anterior, que parece que la aplicación se ha vuelto loca.
  const turno = useRef(0);

  const cargar = useCallback(async () => {
    if (!user) return;
    try {
      setPeticiones(await misPeticiones());
    } catch {
      /* si falla, la lista se queda como estaba */
    } finally {
      setCargando(false);
    }
  }, [user]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const buscar = useCallback(async (q: string) => {
    const limpio = q.trim();
    if (limpio.length < 2) {
      setResultado(null);
      setBuscando(false);
      return;
    }
    const mio = ++turno.current;
    setBuscando(true);
    try {
      const r = await buscarParaPedir(limpio);
      if (mio === turno.current) setResultado(r);
    } catch {
      if (mio === turno.current) setResultado(null);
    } finally {
      if (mio === turno.current) setBuscando(false);
    }
  }, []);

  // Se busca solo mientras se escribe, con una pausa: es lo que hace que la página se sienta viva
  // (y evita preguntarle a YouTube por cada letra).
  useEffect(() => {
    const t = setTimeout(() => void buscar(texto), 600);
    return () => clearTimeout(t);
  }, [texto, buscar]);

  const pedir = async (youtubeId?: string, duracion?: number | null) => {
    const limpio = texto.trim();
    if (limpio.length < 3) {
      message.warning('Escribe al menos el nombre de la canción');
      return;
    }
    setEnviando(youtubeId ?? 'cualquiera');
    try {
      const r = await crearPeticion(limpio, youtubeId, duracion);
      message.success(
        r.repetida
          ? 'Ya la habías pedido: sigue en cola'
          : youtubeId
            ? 'Pedida esa versión: se descargará en la próxima vuelta'
            : 'Pedida: se descargará en la próxima vuelta'
      );
      await cargar();
      await buscar(limpio);
    } catch {
      message.error('No se ha podido pedir (¿sesión caducada?)');
    } finally {
      setEnviando(null);
    }
  };

  const escuchar = (id: number) => {
    void playerService.startPlayback({ context_uri: `radiopv:track:${id}` });
  };

  const resumen = useMemo(() => {
    const enCola = peticiones.filter((p) => p.status === 'pendiente').length;
    const listas = peticiones.filter((p) => p.status === 'descargada').length;
    return { enCola, listas };
  }, [peticiones]);

  if (!user) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          type='info'
          showIcon
          message='Inicia sesión para pedir canciones'
          description='Las peticiones se guardan en tu cuenta para que sepas qué has pedido y cuándo llega.'
        />
      </div>
    );
  }

  const hayAlgo =
    !!resultado &&
    (resultado.en_biblioteca.length > 0 ||
      resultado.en_youtube.length > 0 ||
      resultado.en_cola.length > 0);

  return (
    <div style={{ padding: 16, maxWidth: 820, margin: '0 auto' }}>
      <Title level={2} style={{ marginBottom: 4 }}>
        Pedir una canción
      </Title>
      <Paragraph type='secondary' style={{ marginBottom: 16 }}>
        Busca aquí: primero se mira si ya está en la biblioteca y, si no, se enseñan las versiones
        que hay en YouTube para que elijas la tuya. Vale también para lo que no está en las tiendas
        de música: <b>mashups</b>, <b>remixes</b> y <b>sesiones de DJ</b>.
      </Paragraph>

      <Card size='small' style={{ marginBottom: 16 }}>
        <Input.Search
          size='large'
          placeholder='p. ej. «Bad Bunny x Rosalía» o «sesión de reggaetón viejo»'
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onSearch={(v) => void buscar(v)}
          enterButton='Buscar'
          allowClear
        />

        {/* ---------- lo que YA está en casa ---------- */}
        {resultado && resultado.en_biblioteca.length > 0 && (
          <Alert
            style={{ marginTop: 12 }}
            type='success'
            showIcon
            message='Esto ya está en tu biblioteca'
            description={
              <Space direction='vertical' size={4} style={{ width: '100%' }}>
                {resultado.en_biblioteca.slice(0, 5).map((c) => (
                  <Space key={c.id} size={8} wrap>
                    <Text>
                      <b>{c.artista}</b> — {c.titulo}
                    </Text>
                    {duracionLegible(c.duracion) && (
                      <Text type='secondary' style={{ fontSize: 12 }}>
                        {duracionLegible(c.duracion)}
                      </Text>
                    )}
                    <Button size='small' onClick={() => escuchar(c.id)}>
                      Escuchar
                    </Button>
                  </Space>
                ))}
                <Text type='secondary' style={{ fontSize: 12 }}>
                  Si lo que quieres es otra versión, búscala abajo y pide la que te interese.
                </Text>
              </Space>
            }
          />
        )}

        {/* ---------- lo que ya está pedido ---------- */}
        {resultado && resultado.en_cola.length > 0 && (
          <Alert
            style={{ marginTop: 12 }}
            type='info'
            showIcon
            message='Ya está pedida y sigue en cola'
            description={resultado.en_cola.map((p) => p.text).join(' · ')}
          />
        )}

        {/* ---------- versiones de YouTube ---------- */}
        {buscando && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <Spin size='small' />{' '}
            <Text type='secondary'>Buscando versiones en YouTube…</Text>
          </div>
        )}

        {!buscando && resultado?.aviso && (
          <Alert style={{ marginTop: 12 }} type='warning' showIcon message={resultado.aviso} />
        )}

        {!buscando && resultado && resultado.en_youtube.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Text strong>Versiones encontradas en YouTube</Text>
            <List
              size='small'
              dataSource={resultado.en_youtube}
              renderItem={(r) => (
                <List.Item
                  actions={[
                    r.en_catalogo ? (
                      <Tag key='ya' color='green'>
                        Ya la tienes
                      </Tag>
                    ) : (
                      <Button
                        key='pedir'
                        size='small'
                        type='primary'
                        loading={enviando === r.video_id}
                        onClick={() => void pedir(r.video_id, r.duracion)}
                      >
                        Pedir esta
                      </Button>
                    ),
                  ]}
                >
                  <List.Item.Meta
                    title={<Text strong>{r.titulo}</Text>}
                    description={
                      <Space size={8} wrap>
                        <Text type='secondary' style={{ fontSize: 12 }}>
                          {r.canal || 'canal desconocido'}
                        </Text>
                        {duracionLegible(r.duracion) && (
                          <Tag>{duracionLegible(r.duracion)}</Tag>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </div>
        )}

        {!buscando && resultado && !hayAlgo && (
          <Alert
            style={{ marginTop: 12 }}
            type='warning'
            showIcon
            message='Ni está en la biblioteca ni se ha encontrado en YouTube'
            description='Repasa cómo se escribe, o pídela igualmente y el recolector la buscará con más calma en la próxima vuelta.'
          />
        )}

        {/* ---------- pedir a mano (sin elegir versión) ---------- */}
        <div style={{ marginTop: 16 }}>
          <Space wrap>
            <Tooltip title='La busca el recolector: primero en las tiendas de música y, si no, en YouTube'>
              <Button loading={enviando === 'cualquiera'} onClick={() => void pedir()}>
                {resultado?.en_youtube.length ? 'Que la busque el recolector' : 'Pedir'}
              </Button>
            </Tooltip>
            <Text type='secondary' style={{ fontSize: 12 }}>
              Se pide tal cual está escrito arriba, sin elegir versión.
            </Text>
          </Space>
        </div>
      </Card>

      <Card
        size='small'
        title='Mis peticiones'
        extra={
          <Text type='secondary' style={{ fontSize: 12 }}>
            {resumen.enCola} en cola · {resumen.listas} descargadas
          </Text>
        }
      >
        {cargando ? (
          <Text type='secondary'>Cargando…</Text>
        ) : peticiones.length === 0 ? (
          <Empty description='Todavía no has pedido ninguna canción' />
        ) : (
          <List
            size='small'
            dataSource={peticiones}
            renderItem={(p) => {
              const e = ESTADOS[p.status] ?? {
                color: 'default',
                texto: p.status,
                ayuda: '',
              };
              return (
                <List.Item
                  actions={[
                    p.status === 'descargada' ? (
                      <Button
                        size='small'
                        key='buscar'
                        onClick={() => {
                          setTexto(p.text);
                          void buscar(p.text);
                        }}
                      >
                        Escuchar
                      </Button>
                    ) : null,
                    p.status === 'fallida' ? (
                      <Button
                        size='small'
                        key='reintentar'
                        loading={enviando === 'cualquiera' && texto === p.text}
                        onClick={() => {
                          setTexto(p.text);
                          void pedir();
                        }}
                      >
                        Reintentar
                      </Button>
                    ) : null,
                    <Button
                      size='small'
                      type='text'
                      danger
                      key='quitar'
                      onClick={async () => {
                        await borrarPeticion(p.id);
                        await cargar();
                      }}
                    >
                      Quitar
                    </Button>,
                  ].filter(Boolean)}
                >
                  <List.Item.Meta
                    title={
                      <Space size={8} wrap>
                        <Text strong>{p.text}</Text>
                        <Tag color={e.color}>{e.texto}</Tag>
                      </Space>
                    }
                    description={
                      <Text type='secondary' style={{ fontSize: 12 }}>
                        {e.ayuda}
                        {p.created_at ? ` · pedida el ${p.created_at.replace('T', ' ')}` : ''}
                      </Text>
                    }
                  />
                </List.Item>
              );
            }}
          />
        )}
      </Card>

      {/* Decía «el recolector que corre en el PC de casa»: desde el 20/09/2026 las descargas las
        * hace el propio servidor (el PC dejó de encargarse de eso), así que el texto mentía. */}
      <Paragraph type='secondary' style={{ fontSize: 12, marginTop: 12 }}>
        Las peticiones las atiende el recolector del propio servidor, cada 15 minutos.
      </Paragraph>
    </div>
  );
};

export default PedirCanciones;
