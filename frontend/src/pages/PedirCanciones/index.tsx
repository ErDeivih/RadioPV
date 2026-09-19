import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Empty, Input, List, Space, Tag, Typography, message } from 'antd';

// Services
import {
  borrarPeticion,
  crearPeticion,
  misPeticiones,
  yaEstaEnLaBiblioteca,
  type Peticion,
} from '../../services/peticiones';

// Utilidades
import { useNavigate } from 'react-router-dom';

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
 * POR QUÉ
 * -------
 * La app podía crear peticiones desde que existe la tabla `requests`, pero **nadie las consumía**:
 * se quedaban en «pendiente» para siempre. Ahora el recolector del PC las recoge, las busca y
 * contesta. Y sirve para lo que más se pide: mashups, remixes y sesiones de DJ, que no están en
 * las tiendas de música y se buscan directamente en YouTube.
 *
 * La página avisa antes de pedir si la canción ya está: buscar y no encontrarla es normal (el
 * catálogo es lo que es), pero pedir algo que ya tienes sería culpa nuestra.
 */
export const PedirCanciones: FC = () => {
  const navigate = useNavigate();
  const user = useAppSelector((state) => state.auth.user);

  const [texto, setTexto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [peticiones, setPeticiones] = useState<Peticion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [coincidencias, setCoincidencias] = useState<{ id: number; title: string; artist: string }[]>([]);

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

  // Mientras se escribe: ¿ya está en la biblioteca? Se espera un poco para no preguntar por cada
  // letra (el catálogo está en el servidor de casa, pero no hace falta machacarlo).
  useEffect(() => {
    const t = setTimeout(() => {
      yaEstaEnLaBiblioteca(texto)
        .then(setCoincidencias)
        .catch(() => setCoincidencias([]));
    }, 450);
    return () => clearTimeout(t);
  }, [texto]);

  const pedir = async () => {
    const limpio = texto.trim();
    if (limpio.length < 3) {
      message.warning('Escribe al menos el nombre de la canción');
      return;
    }
    setEnviando(true);
    try {
      const r = await crearPeticion(limpio);
      message.success(
        r.repetida ? 'Ya la habías pedido: sigue en cola' : 'Pedida: se descargará en la próxima vuelta'
      );
      setTexto('');
      setCoincidencias([]);
      await cargar();
    } catch {
      message.error('No se ha podido pedir (¿sesión caducada?)');
    } finally {
      setEnviando(false);
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

  return (
    <div style={{ padding: 16, maxWidth: 760, margin: '0 auto' }}>
      <Title level={2} style={{ marginBottom: 4 }}>
        Pedir una canción
      </Title>
      <Paragraph type='secondary' style={{ marginBottom: 16 }}>
        Si no está en la biblioteca, pídela y se descargará sola. Vale también para lo que no está
        en las tiendas de música: <b>mashups</b>, <b>remixes</b> y <b>sesiones de DJ</b>. Escríbelo
        como quieras —«Artista - Canción», «Canción A x Canción B», «Sesión de reggaetón viejo»— y
        se busca tal cual.
      </Paragraph>

      <Card size='small' style={{ marginBottom: 16 }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            size='large'
            placeholder='p. ej. «Bad Bunny x Rosalía» o «sesión de reggaetón viejo»'
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onPressEnter={() => void pedir()}
            allowClear
          />
          <Button size='large' type='primary' loading={enviando} onClick={() => void pedir()}>
            Pedir
          </Button>
        </Space.Compact>

        {coincidencias.length > 0 && (
          <Alert
            style={{ marginTop: 12 }}
            type='success'
            showIcon
            message='Esto ya está en tu biblioteca'
            description={
              <Space direction='vertical' size={4} style={{ width: '100%' }}>
                {coincidencias.map((c) => (
                  <Space key={c.id} size={8} wrap>
                    <Text>
                      <b>{c.artist}</b> — {c.title}
                    </Text>
                    <Button size='small' onClick={() => escuchar(c.id)}>
                      Escuchar
                    </Button>
                  </Space>
                ))}
                <Text type='secondary'>Si lo que quieres es otra versión, pídelo igualmente.</Text>
              </Space>
            }
          />
        )}
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
                        onClick={() =>
                          navigate(`/search/${encodeURIComponent(p.text.split(' - ')[0] ?? '')}`)
                        }
                      >
                        Buscar
                      </Button>
                    ) : null,
                    <Button
                      size='small'
                      type='text'
                      danger
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
    </div>
  );
};

export default PedirCanciones;
