import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Input,
  Popconfirm,
  Segmented,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { adminApi, BlacklistEntry } from './api';

const { Text } = Typography;

/** Lista negra: lo que está aquí no se volverá a descargar. */
export const Blacklist: FC = () => {
  const [filas, setFilas] = useState<BlacklistEntry[]>([]);
  const [cargando, setCargando] = useState(true);
  const [tipo, setTipo] = useState<'todas' | 'artist' | 'song'>('todas');
  const [busca, setBusca] = useState('');

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const kind = tipo === 'todas' ? undefined : tipo;
      setFilas(await adminApi.blacklist(kind));
    } catch {
      message.error('No se pudo leer la lista negra');
    } finally {
      setCargando(false);
    }
  }, [tipo]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const retirar = async (id: number) => {
    try {
      await adminApi.removeBlacklist(id);
      setFilas((prev) => prev.filter((f) => f.id !== id));
      message.success('Retirado de la lista negra');
    } catch {
      message.error('No se pudo retirar');
    }
  };

  const purgar = async () => {
    try {
      const r = await adminApi.purge();
      message.success(`Purgadas ${r.purgadas ?? 0} canciones del disco`);
      void cargar();
    } catch {
      message.error('No se pudo purgar');
    }
  };

  const visibles = useMemo(() => {
    if (!busca.trim()) return filas;
    const q = busca.toLowerCase();
    return filas.filter((f) => f.value.toLowerCase().includes(q));
  }, [filas, busca]);

  const columnas: ColumnsType<BlacklistEntry> = [
    {
      title: 'Tipo',
      dataIndex: 'kind',
      width: 110,
      filters: [
        { text: 'Artista', value: 'artist' },
        { text: 'Canción', value: 'song' },
      ],
      onFilter: (v, r) => r.kind === v,
      render: (v: string) =>
        v === 'artist' ? <Tag color='volcano'>Artista</Tag> : <Tag color='blue'>Canción</Tag>,
    },
    { title: 'Valor', dataIndex: 'value', render: (v: string) => <Text strong>{v}</Text> },
    { title: 'Motivo', dataIndex: 'reason', responsive: ['md'] },
    { title: 'Añadido', dataIndex: 'created_at', width: 180, responsive: ['lg'] },
    {
      title: '',
      width: 100,
      render: (_, r) => (
        <Button size='small' danger onClick={() => void retirar(r.id)}>
          Retirar
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Alert
        style={{ marginBottom: 16 }}
        type='info'
        showIcon
        message='Lo que está en esta lista NO se volverá a descargar'
        description='Al vetar una canción o un artista, el recolector lo omite en todas sus búsquedas. Vetar un artista además borra sus canciones de la biblioteca.'
      />

      <Card
        title={`Lista negra · ${visibles.length} entradas`}
        extra={
          <Space wrap>
            <Segmented
              value={tipo}
              onChange={(v) => setTipo(v as typeof tipo)}
              options={[
                { label: 'Todas', value: 'todas' },
                { label: 'Artistas', value: 'artist' },
                { label: 'Canciones', value: 'song' },
              ]}
            />
            <Input.Search
              placeholder='Buscar…'
              allowClear
              onChange={(e) => setBusca(e.target.value)}
              style={{ width: 200 }}
            />
            <Button onClick={() => void cargar()}>Recargar</Button>
            <Popconfirm
              title='¿Borrar del disco todo lo vetado?'
              description='Elimina los ficheros de las canciones vetadas que sigan en la biblioteca. La lista negra se conserva.'
              okText='Sí, purgar'
              cancelText='Cancelar'
              onConfirm={() => void purgar()}
            >
              <Button danger>Purgar vetados</Button>
            </Popconfirm>
          </Space>
        }
      >
        <Table<BlacklistEntry>
          rowKey='id'
          size='small'
          loading={cargando}
          columns={columnas}
          dataSource={visibles}
          pagination={{ pageSize: 50, showSizeChanger: true }}
        />
      </Card>
    </div>
  );
};

export default Blacklist;
