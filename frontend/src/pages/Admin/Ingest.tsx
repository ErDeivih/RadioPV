import { FC, useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  List,
  Row,
  Spin,
  Statistic,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd';
import { adminApi, AdminStatus, EventRow } from './api';

const { Text, Title } = Typography;

/** Interruptor de la ingesta + diario de eventos del recolector. */
export const Ingest: FC = () => {
  const [estado, setEstado] = useState<AdminStatus | null>(null);
  const [eventos, setEventos] = useState<EventRow[]>([]);
  const [cargando, setCargando] = useState(true);
  const [cambiando, setCambiando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([adminApi.status(), adminApi.events(80)]);
      setEstado(s);
      setEventos(e);
    } catch {
      message.error('No se pudo leer el estado del recolector');
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargar();
    const t = setInterval(() => void cargar(), 15000);
    return () => clearInterval(t);
  }, [cargar]);

  const cambiar = async (activar: boolean) => {
    setCambiando(true);
    try {
      const nuevo = await adminApi.setIngest(activar);
      setEstado((prev) => (prev ? { ...prev, ingesta: nuevo } : prev));
      message.success(activar ? 'Ingesta ACTIVADA' : 'Ingesta DESACTIVADA');
    } catch {
      message.error('No se pudo cambiar el estado de la ingesta');
    } finally {
      setCambiando(false);
    }
  };

  if (cargando) return <Spin style={{ margin: 40 }} />;

  const activa = estado?.ingesta.enabled ?? false;

  return (
    <div style={{ padding: 16 }}>
      <Card
        style={{ marginBottom: 16, borderColor: activa ? '#52c41a' : '#d9d9d9' }}
        title={
          <Row align='middle' gutter={16}>
            <Col flex='auto'>
              <Title level={4} style={{ margin: 0 }}>
                {activa ? '🟢 Ingesta activa' : '⚪ Ingesta detenida'}
              </Title>
            </Col>
            <Col>
              <Switch
                checked={activa}
                loading={cambiando}
                onChange={cambiar}
                checkedChildren='ACTIVA'
                unCheckedChildren='PARADA'
              />
            </Col>
          </Row>
        }
      >
        <Alert
          type={activa ? 'success' : 'info'}
          showIcon
          message={
            activa
              ? 'El recolector está buscando y descargando música nueva.'
              : 'El recolector no buscará ni descargará nada nuevo. La biblioteca sigue intacta.'
          }
          description={
            estado?.ingesta.updated_at ? (
              <Text type='secondary'>
                Último cambio: {estado.ingesta.updated_at}
                {estado.ingesta.updated_by ? ` · por ${estado.ingesta.updated_by}` : ''}
              </Text>
            ) : (
              <Text type='secondary'>Nunca se ha tocado este interruptor.</Text>
            )
          }
        />
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title='Pistas en la biblioteca' value={estado?.tracks_total ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title='Tamaño de la biblioteca'
              value={estado?.biblioteca_gb ?? 0}
              suffix='GB'
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title='Vetados' value={estado?.vetados ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title='Libre en el disco de música'
              value={estado?.disco?.libre_gb ?? 0}
              suffix='GB'
            />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }} title='Por estado'>
        {(estado?.tracks_por_estado ?? []).map((e) => (
          <Tag key={String(e.status)} style={{ marginBottom: 6 }}>
            {e.status ?? 'sin estado'}: <b>{e.n}</b>
          </Tag>
        ))}
      </Card>

      <Card
        title='Diario del recolector'
        extra={<Button onClick={() => void cargar()}>Recargar</Button>}
      >
        <List
          size='small'
          dataSource={eventos}
          style={{ maxHeight: 420, overflow: 'auto' }}
          renderItem={(e) => (
            <List.Item>
              <Text type='secondary' style={{ marginRight: 12, whiteSpace: 'nowrap' }}>
                {e.ts}
              </Text>
              <Text>{e.message}</Text>
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
};

export default Ingest;
