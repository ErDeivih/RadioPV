import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  adminApi,
  BulkFilter,
  GroupBy,
  GroupRow,
  labelGenre,
  labelLang,
  BulkResult,
} from './api';

const { Text } = Typography;

const PAGINA = 200;

export interface Props {
  /** Campo por el que agrupar. */
  by: GroupBy;
  /** Filtros activos en la pestaña (idioma, género, artista, años, texto…). */
  filtros: BulkFilter;
  /** Se llama cuando algo cambia en la biblioteca, para refrescar los contadores. */
  onHecho: () => void;
}

/** Nombre del campo de lista que corresponde a cada agrupación. */
const CAMPO_LISTA: Partial<Record<GroupBy, keyof BulkFilter>> = {
  artist: 'artists',
  album: 'albums',
  genre: 'genres',
  language: 'languages',
  year: 'years',
};

const ETIQUETA: Record<string, string> = {
  artist: 'artista',
  album: 'álbum',
  genre: 'género',
  language: 'idioma',
  year: 'año',
  status: 'estado',
  source: 'origen',
};

/**
 * Vista agrupada de la biblioteca: **una fila por artista / álbum / género / idioma / año**.
 *
 * Es la herramienta para limpiar rápido: filtras por idioma, ves *"412 artistas"*, marcas
 * los que no quieras y los **vetas y borras de un clic**. Cada acción borra los ficheros
 * del disco y registra el veto en la lista negra, para que el recolector no los vuelva a
 * bajar nunca.
 *
 * Todas las operaciones se previsualizan antes (`dry_run`) para que veas cuántas canciones
 * caen sin tocar nada.
 */
export const GroupsTable: FC<Props> = ({ by, filtros, onHecho }) => {
  const [filas, setFilas] = useState<GroupRow[]>([]);
  const [totalGrupos, setTotalGrupos] = useState(0);
  const [pagina, setPagina] = useState(1);
  const [cargando, setCargando] = useState(false);
  const [seleccion, setSeleccion] = useState<string[]>([]);
  const [minTracks, setMinTracks] = useState(1);
  const [veto, setVeto] = useState(true);
  const [confirmacion, setConfirmacion] = useState<
    (BulkResult & { accion: 'delete' | 'blacklist' }) | null
  >(null);
  const [ejecutando, setEjecutando] = useState(false);

  const campoLista = CAMPO_LISTA[by];

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const r = await adminApi.group({
        by,
        ...filtros,
        min_tracks: minTracks,
        limit: PAGINA,
        offset: (pagina - 1) * PAGINA,
      });
      setFilas(r.items);
      setTotalGrupos(r.total_grupos);
    } catch {
      message.error('No se pudo agrupar la biblioteca');
    } finally {
      setCargando(false);
    }
  }, [by, filtros, minTracks, pagina]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Al cambiar de agrupación o de filtros, empezamos de cero
  useEffect(() => {
    setPagina(1);
    setSeleccion([]);
  }, [by, filtros, minTracks]);

  const claves = useMemo(
    () => filas.map((f) => String(f.valor ?? '')),
    [filas]
  );
  const todosSeleccionados = claves.length > 0 && seleccion.length === claves.length;

  const cancionesSeleccionadas = useMemo(
    () =>
      filas
        .filter((f) => seleccion.includes(String(f.valor ?? '')))
        .reduce((acc, f) => acc + f.n, 0),
    [filas, seleccion]
  );

  const bytesSeleccionados = useMemo(
    () =>
      filas
        .filter((f) => seleccion.includes(String(f.valor ?? '')))
        .reduce((acc, f) => acc + (f.size ?? 0), 0),
    [filas, seleccion]
  );

  /** Traduce la selección de grupos al filtro de lista que espera el backend. */
  const filtroDeSeleccion = (): BulkFilter | null => {
    if (!campoLista || !seleccion.length) return null;
    if (by === 'year') {
      const anios = seleccion.map((s) => Number(s)).filter((n) => Number.isFinite(n));
      return { ...filtros, years: anios };
    }
    return { ...filtros, [campoLista]: seleccion } as BulkFilter;
  };

  const previsualizar = async (accion: 'delete' | 'blacklist') => {
    const f = filtroDeSeleccion();
    if (!f) {
      message.warning(`Selecciona al menos un ${ETIQUETA[by] ?? 'elemento'}`);
      return;
    }
    setEjecutando(true);
    try {
      const r = await adminApi.bulk(f, accion, veto, true);
      if (r.afectadas === 0) {
        message.info('No hay canciones en esa selección');
        return;
      }
      setConfirmacion({ ...r, accion });
    } catch {
      message.error('No se pudo previsualizar');
    } finally {
      setEjecutando(false);
    }
  };

  const ejecutar = async () => {
    const f = filtroDeSeleccion();
    if (!f || !confirmacion) return;
    setEjecutando(true);
    try {
      const r = await adminApi.bulk(f, confirmacion.accion, veto, false);
      message.success(
        confirmacion.accion === 'blacklist'
          ? `Vetadas ${r.vetadas} canciones (ficheros conservados)`
          : `Borradas ${r.borradas} canciones${r.vetadas ? ' y añadidas a la lista negra' : ''}`
      );
      setConfirmacion(null);
      setSeleccion([]);
      void cargar();
      onHecho();
    } catch {
      message.error('La operación falló');
    } finally {
      setEjecutando(false);
    }
  };

  const columnas: ColumnsType<GroupRow> = [
    {
      title: ETIQUETA[by] ?? by,
      dataIndex: 'valor',
      ellipsis: true,
      render: (v: string | number | null) => {
        if (by === 'language') return <Text strong>{labelLang(String(v))}</Text>;
        if (by === 'genre') return <Text strong>{labelGenre(String(v))}</Text>;
        if (v === null || v === '') return <Text type='secondary'>(sin dato)</Text>;
        return <Text strong>{String(v)}</Text>;
      },
    },
    {
      title: 'Canciones',
      dataIndex: 'n',
      width: 110,
      sorter: (a, b) => a.n - b.n,
      render: (v: number) => <Tag color='blue'>{v.toLocaleString('es-ES')}</Tag>,
    },
    {
      title: 'Tamaño',
      dataIndex: 'size',
      width: 110,
      render: (v: number) => (v ? `${(v / 1024 ** 3).toFixed(2)} GB` : '—'),
    },
    {
      title: 'Idiomas',
      dataIndex: 'languages',
      width: 160,
      responsive: ['lg'],
      render: (v: string | null) =>
        v ? v.split(',').map((l) => <Tag key={l}>{labelLang(l)}</Tag>) : '—',
    },
    {
      title: 'Géneros',
      dataIndex: 'genres',
      ellipsis: true,
      responsive: ['xl'],
      render: (v: string | null) =>
        v ? v.split(',').slice(0, 4).map((g) => <Tag key={g}>{labelGenre(g)}</Tag>) : '—',
    },
    {
      title: 'Años',
      width: 120,
      responsive: ['lg'],
      render: (_, r) =>
        r.year_min && r.year_max
          ? r.year_min === r.year_max
            ? String(r.year_min)
            : `${r.year_min}–${r.year_max}`
          : '—',
    },
  ];

  const etiqueta = ETIQUETA[by] ?? 'elemento';

  return (
    <>
      <Card
        size='small'
        style={{ marginBottom: 16 }}
        title={
          <Space wrap>
            <Text strong>
              {totalGrupos.toLocaleString('es-ES')} {etiqueta}s
            </Text>
            {seleccion.length > 0 && (
              <Tag color='blue'>
                {seleccion.length} seleccionados · {cancionesSeleccionadas.toLocaleString('es-ES')}{' '}
                canciones · {(bytesSeleccionados / 1024 ** 3).toFixed(2)} GB
              </Tag>
            )}
          </Space>
        }
      >
        <Space wrap style={{ marginBottom: 12 }}>
          <Button
            onClick={() => setSeleccion(todosSeleccionados ? [] : claves)}
            disabled={!claves.length}
          >
            {todosSeleccionados ? 'Quitar selección de esta página' : 'Seleccionar esta página'}
          </Button>
          <Text type='secondary'>Ocultar los que tengan menos de</Text>
          <Tag.CheckableTag checked={minTracks === 1} onChange={() => setMinTracks(1)}>
            1
          </Tag.CheckableTag>
          <Tag.CheckableTag checked={minTracks === 3} onChange={() => setMinTracks(3)}>
            3
          </Tag.CheckableTag>
          <Tag.CheckableTag checked={minTracks === 10} onChange={() => setMinTracks(10)}>
            10
          </Tag.CheckableTag>
          <Text type='secondary'>canciones</Text>
        </Space>

        <Space wrap>
          <Tooltip title='Se borran los ficheros del disco Y se registran en la lista negra, para que no se vuelvan a descargar'>
            <Space>
              <Switch checked={veto} onChange={setVeto} size='small' />
              <Text type={veto ? undefined : 'secondary'}>
                Vetar al borrar {veto ? '(recomendado)' : '(no se vetará)'}
              </Text>
            </Space>
          </Tooltip>

          <Button
            type='primary'
            danger
            loading={ejecutando}
            disabled={!seleccion.length}
            onClick={() => void previsualizar('delete')}
          >
            Vetar y borrar los seleccionados
          </Button>

          <Button
            danger
            loading={ejecutando}
            disabled={!seleccion.length}
            onClick={() => void previsualizar('blacklist')}
          >
            Solo vetar (conservar ficheros)
          </Button>

          <Button onClick={() => setSeleccion([])} disabled={!seleccion.length}>
            Quitar selección
          </Button>
        </Space>

        {!seleccion.length && (
          <Alert
            style={{ marginTop: 12 }}
            type='info'
            showIcon
            message={`Marca los ${etiqueta}s que no quieras y pulsa «Vetar y borrar los seleccionados»`}
            description='Cada operación te muestra antes cuántas canciones van a caer, para que no borres a ciegas.'
          />
        )}
      </Card>

      <Table<GroupRow>
        rowKey={(r) => String(r.valor ?? '')}
        size='small'
        loading={cargando}
        columns={columnas}
        dataSource={filas}
        scroll={{ x: 900 }}
        rowSelection={{
          selectedRowKeys: seleccion,
          onChange: (keys) => setSeleccion(keys as string[]),
        }}
        pagination={{
          current: pagina,
          pageSize: PAGINA,
          total: totalGrupos,
          showSizeChanger: false,
          onChange: setPagina,
          showTotal: (t) => `${t.toLocaleString('es-ES')} ${etiqueta}s`,
        }}
      />

      <Modal
        open={Boolean(confirmacion)}
        title={
          confirmacion?.accion === 'blacklist'
            ? '⚠️ Vetar sin borrar'
            : '⚠️ Vetar y borrar'
        }
        okText={confirmacion?.accion === 'blacklist' ? 'Vetar ahora' : 'Vetar y borrar'}
        okButtonProps={{ danger: true, loading: ejecutando }}
        cancelText='Cancelar'
        onOk={() => void ejecutar()}
        onCancel={() => setConfirmacion(null)}
      >
        <Alert
          type='warning'
          showIcon
          style={{ marginBottom: 16 }}
          message={
            confirmacion?.accion === 'blacklist'
              ? `${confirmacion?.afectadas.toLocaleString('es-ES')} canciones se van a VETAR (los ficheros se conservan)`
              : `${confirmacion?.afectadas.toLocaleString('es-ES')} canciones se van a BORRAR del disco`
          }
          description={
            confirmacion?.accion === 'blacklist'
              ? 'No se libera espacio, pero el recolector no las volverá a descargar.'
              : 'Se eliminan los ficheros y las filas de la base, y quedan registradas en la lista negra.'
          }
        />
        <Text strong>Selección ({seleccion.length} {etiqueta}s):</Text>
        <div style={{ maxHeight: 260, overflow: 'auto', marginTop: 8 }}>
          {seleccion.map((s) => (
            <Tag key={s} style={{ marginBottom: 4 }}>
              {by === 'language' ? labelLang(s) : by === 'genre' ? labelGenre(s) : s}
            </Tag>
          ))}
        </div>
        {confirmacion?.accion === 'delete' && (
          <Space style={{ marginTop: 12 }}>
            <Switch checked={veto} onChange={setVeto} />
            <Text>
              Registrarlas en la lista negra para que <b>no se vuelvan a descargar</b>
            </Text>
          </Space>
        )}
      </Modal>
    </>
  );
};

export default GroupsTable;
