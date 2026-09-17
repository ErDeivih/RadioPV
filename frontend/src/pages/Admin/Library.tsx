import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Select,
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
  duracion,
  Facets,
  labelGenre,
  labelLang,
  labelStatus,
  mb,
  TrackFilters,
  TrackRow,
  GroupBy,
} from './api';
import GroupsTable from './GroupsTable';

const { Text, Title } = Typography;

const PAGINA = 100;

/**
 * Gestión de la biblioteca: filtrar y borrar en masa.
 *
 * Dos formas de borrar, pensadas para cosas distintas:
 *  · **Por selección** — marcas filas concretas y actúas sobre ellas (pocas canciones).
 *  · **Por filtro** — *"todo lo que no sea español"*, *"todo el género X"*. Es la que
 *    sirve para limpiar miles de canciones de golpe: no manda IDs, el servidor resuelve.
 *
 * La operación por filtro siempre se previsualiza antes (dry-run), así nunca borras a ciegas.
 */
export const Library: FC = () => {
  const [filas, setFilas] = useState<TrackRow[]>([]);
  const [total, setTotal] = useState(0);
  const [pagina, setPagina] = useState(1);
  const [cargando, setCargando] = useState(false);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [seleccion, setSeleccion] = useState<number[]>([]);
  const [vetoPorDefecto, setVetoPorDefecto] = useState(true);

  // Filtros
  const [q, setQ] = useState('');
  const [language, setLanguage] = useState<string | undefined>();
  const [genre, setGenre] = useState<string | undefined>();
  const [artist, setArtist] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [yearMin, setYearMin] = useState<number | undefined>();
  const [yearMax, setYearMax] = useState<number | undefined>();

  // Vista: lista plana de canciones, o agrupada (por artista, álbum, género, idioma, año)
  const [vista, setVista] = useState<'tracks' | GroupBy>('tracks');

  // Confirmación del borrado en masa
  const [confirmacion, setConfirmacion] = useState<{
    afectadas: number;
    accion: 'delete' | 'blacklist';
  } | null>(null);
  const [vetoConfirmado, setVetoConfirmado] = useState(true);
  const [ejecutando, setEjecutando] = useState(false);

  /** Filtros en el formato que espera la API. */
  const filtros = useMemo<TrackFilters>(
    () => ({
      q: q.trim() || undefined,
      language,
      genre,
      artist,
      status,
      year_min: yearMin,
      year_max: yearMax,
    }),
    [q, language, genre, artist, status, yearMin, yearMax]
  );

  const filtrosBulk = useMemo<BulkFilter>(
    () => ({ ...filtros }),
    [filtros]
  );

  /** ¿Hay algún filtro puesto? Sin filtro NO se permite borrado en masa. */
  const hayFiltro = useMemo(
    () =>
      Boolean(
        q.trim() ||
          language ||
          genre ||
          artist ||
          status ||
          yearMin !== undefined ||
          yearMax !== undefined
      ),
    [q, language, genre, artist, status, yearMin, yearMax]
  );

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const r = await adminApi.tracks({ ...filtros, limit: PAGINA, offset: (pagina - 1) * PAGINA });
      setFilas(r.items);
      setTotal(r.total);
    } catch {
      message.error('No se pudo cargar la biblioteca');
    } finally {
      setCargando(false);
    }
  }, [filtros, pagina]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  useEffect(() => {
    adminApi
      .facets()
      .then(setFacets)
      .catch(() => message.warning('No se pudieron cargar los filtros'));
  }, []);

  // Al cambiar un filtro volvemos a la primera página y soltamos la selección
  useEffect(() => {
    setPagina(1);
    setSeleccion([]);
  }, [language, genre, artist, status, yearMin, yearMax]);

  const limpiarFiltros = () => {
    setQ('');
    setLanguage(undefined);
    setGenre(undefined);
    setArtist(undefined);
    setStatus(undefined);
    setYearMin(undefined);
    setYearMax(undefined);
  };

  // ------------------------------------------------------------------ acciones
  const borrarSeleccion = async () => {
    if (!seleccion.length) return;
    try {
      const r = await adminApi.deleteTracks(seleccion, vetoPorDefecto);
      message.success(
        `Borradas ${r.borradas} canciones${r.vetadas ? ' y añadidas a la lista negra' : ''}`
      );
      setSeleccion([]);
      void cargar();
    } catch {
      message.error('No se pudieron borrar');
    }
  };

  const vetarSeleccion = async () => {
    if (!seleccion.length) return;
    try {
      const r = await adminApi.blacklistTracks(seleccion);
      message.success(`Vetadas ${r.vetadas} canciones (sin borrar)`);
      setSeleccion([]);
    } catch {
      message.error('No se pudieron vetar');
    }
  };

  /** Paso 1: previsualizar (dry-run). Paso 2: ejecutar desde el modal. */
  const previsualizar = async (accion: 'delete' | 'blacklist') => {
    if (!hayFiltro) {
      message.warning('Pon al menos un filtro antes de usar el borrado en masa');
      return;
    }
    setEjecutando(true);
    try {
      const r = await adminApi.bulk(filtrosBulk, accion, vetoPorDefecto, true);
      if (r.afectadas === 0) {
        message.info('Ninguna canción coincide con esos filtros');
        return;
      }
      setVetoConfirmado(vetoPorDefecto);
      setConfirmacion({ afectadas: r.afectadas, accion });
    } catch {
      message.error('No se pudo previsualizar');
    } finally {
      setEjecutando(false);
    }
  };

  const ejecutarBulk = async () => {
    if (!confirmacion) return;
    setEjecutando(true);
    try {
      const r = await adminApi.bulk(
        filtrosBulk,
        confirmacion.accion,
        vetoConfirmado,
        false
      );
      message.success(
        confirmacion.accion === 'blacklist'
          ? `Vetadas ${r.vetadas} canciones`
          : `Borradas ${r.borradas} canciones${r.vetadas ? ' y vetadas' : ''}`
      );
      setConfirmacion(null);
      setSeleccion([]);
      void cargar();
    } catch {
      message.error('La operación falló');
    } finally {
      setEjecutando(false);
    }
  };

  const vetarArtista = async (nombre: string) => {
    try {
      const r = await adminApi.vetoArtist(nombre, true);
      message.success(`Artista vetado: ${nombre} (${r.borradas} canciones borradas)`);
      void cargar();
    } catch {
      message.error('No se pudo vetar el artista');
    }
  };

  // ------------------------------------------------------------------ columnas
  const columnas: ColumnsType<TrackRow> = [
    {
      title: 'Título',
      dataIndex: 'title',
      ellipsis: true,
      sorter: true,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'Artista',
      dataIndex: 'artist',
      width: 180,
      ellipsis: true,
      render: (v: string) => (
        <Tooltip title={`Filtrar por ${v}`}>
          <a onClick={() => setArtist(v)}>{v}</a>
        </Tooltip>
      ),
    },
    { title: 'Álbum', dataIndex: 'album', ellipsis: true, responsive: ['lg'] },
    { title: 'Año', dataIndex: 'year', width: 70, responsive: ['md'] },
    {
      title: 'Género',
      dataIndex: 'genre',
      width: 130,
      responsive: ['md'],
      render: (v: string | null) => (v ? <Tag>{labelGenre(v)}</Tag> : '—'),
    },
    {
      title: 'Idioma',
      dataIndex: 'language',
      width: 110,
      render: (v: string | null) => (
        <Tag color={v === 'es' ? 'green' : v === 'other' ? 'orange' : 'blue'}>{labelLang(v)}</Tag>
      ),
    },
    { title: 'Dur.', dataIndex: 'duration', width: 70, responsive: ['lg'], render: duracion },
    {
      title: 'MB',
      dataIndex: 'file_size',
      width: 80,
      responsive: ['lg'],
      render: (v: number | null) => (v ? (v / 1024 / 1024).toFixed(1) : '—'),
    },
    {
      title: 'Estado',
      dataIndex: 'status',
      width: 110,
      render: (v: string | null) => <Tag color={v === 'descargada' ? 'green' : 'default'}>{labelStatus(v)}</Tag>,
    },
    {
      title: '',
      width: 90,
      fixed: 'right',
      render: (_, r) => (
        <Space size={4}>
          <Popconfirm
            title='¿Borrar esta canción?'
            description={`${r.artist} — ${r.title}`}
            okText='Borrar'
            okButtonProps={{ danger: true }}
            cancelText='No'
            onConfirm={async () => {
              await adminApi.deleteTracks([r.id], vetoPorDefecto);
              message.success('Borrada');
              void cargar();
            }}
          >
            <Button size='small' danger>
              Borrar
            </Button>
          </Popconfirm>
          <Tooltip title={`Vetar a ${r.artist} (borra todas sus canciones)`}>
            <Button size='small' onClick={() => void vetarArtista(r.artist)}>
              Vetar
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ];

  const opciones = (items?: { valor: string; n: number }[], etiqueta?: (v: string) => string) =>
    (items ?? []).map((i) => ({
      value: i.valor,
      label: `${etiqueta ? etiqueta(i.valor) : i.valor} (${i.n})`,
    }));

  return (
    <div style={{ padding: 16 }}>
      {/* ---------------------------------------------------------- filtros */}
      <Card size='small' style={{ marginBottom: 16 }}>
        <Row gutter={[8, 8]} align='middle'>
          <Col xs={24} md={6}>
            <Input.Search
              placeholder='Título, artista o álbum…'
              allowClear
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onSearch={() => void cargar()}
            />
          </Col>
          <Col xs={12} md={3}>
            <Select
              style={{ width: '100%' }}
              placeholder='Idioma'
              allowClear
              value={language}
              onChange={setLanguage}
              options={opciones(facets?.languages, labelLang)}
            />
          </Col>
          <Col xs={12} md={3}>
            <Select
              style={{ width: '100%' }}
              placeholder='Género'
              allowClear
              showSearch
              value={genre}
              onChange={setGenre}
              options={opciones(facets?.genres, labelGenre)}
            />
          </Col>
          <Col xs={12} md={3}>
            <Select
              style={{ width: '100%' }}
              placeholder='Artista'
              allowClear
              showSearch
              value={artist}
              onChange={setArtist}
              options={opciones(facets?.artists)}
            />
          </Col>
          <Col xs={12} md={2}>
            <Select
              style={{ width: '100%' }}
              placeholder='Estado'
              allowClear
              value={status}
              onChange={setStatus}
              options={opciones(facets?.status, labelStatus)}
            />
          </Col>
          <Col xs={8} md={2}>
            <InputNumber
              style={{ width: '100%' }}
              placeholder='Año desde'
              value={yearMin}
              onChange={(v) => setYearMin(v ?? undefined)}
            />
          </Col>
          <Col xs={8} md={2}>
            <InputNumber
              style={{ width: '100%' }}
              placeholder='Año hasta'
              value={yearMax}
              onChange={(v) => setYearMax(v ?? undefined)}
            />
          </Col>
          <Col>
            <Space>
              <Button onClick={limpiarFiltros}>Limpiar</Button>
              <Button onClick={() => void cargar()}>Recargar</Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* ---------------------------------------------------------- vista */}
      <div style={{ marginBottom: 16 }}>
        <Segmented
          value={vista}
          onChange={(v) => setVista(v as 'tracks' | GroupBy)}
          options={[
            { label: 'Canciones', value: 'tracks' },
            { label: 'Por artista', value: 'artist' },
            { label: 'Por álbum', value: 'album' },
            { label: 'Por género', value: 'genre' },
            { label: 'Por idioma', value: 'language' },
            { label: 'Por año', value: 'year' },
          ]}
        />
      </div>

      {vista !== 'tracks' ? (
        <GroupsTable by={vista as GroupBy} filtros={filtrosBulk} onHecho={cargar} />
      ) : (
        <>
      {/* ---------------------------------------------------------- acciones en masa */}
      <Card
        size='small'
        style={{ marginBottom: 16 }}
        title={
          <Space wrap>
            <Text strong>
              {total.toLocaleString('es-ES')} canciones
              {hayFiltro ? ' con estos filtros' : ' en total'}
            </Text>
            {seleccion.length > 0 && (
              <Tag color='blue'>{seleccion.length} seleccionadas</Tag>
            )}
          </Space>
        }
      >
        <Space wrap>
          <Tooltip title='Al borrar, añadirlas a la lista negra para que no se vuelvan a descargar'>
            <Space>
              <Switch checked={vetoPorDefecto} onChange={setVetoPorDefecto} size='small' />
              <Text type={vetoPorDefecto ? undefined : 'secondary'}>
                Vetar al borrar {vetoPorDefecto ? '(recomendado)' : '(no se vetará)'}
              </Text>
            </Space>
          </Tooltip>
        </Space>

        <div style={{ marginTop: 12 }}>
          <Space wrap>
            <Popconfirm
              title={`¿Borrar ${seleccion.length} seleccionadas?`}
              okText='Borrar'
              okButtonProps={{ danger: true }}
              cancelText='No'
              disabled={!seleccion.length}
              onConfirm={() => void borrarSeleccion()}
            >
              <Button danger disabled={!seleccion.length}>
                Borrar seleccionadas
              </Button>
            </Popconfirm>

            <Button disabled={!seleccion.length} onClick={() => void vetarSeleccion()}>
              Vetar seleccionadas
            </Button>

            <Button
              type='primary'
              danger
              loading={ejecutando}
              disabled={!hayFiltro}
              onClick={() => void previsualizar('delete')}
            >
              Borrar TODO lo filtrado
            </Button>

            <Button
              danger
              loading={ejecutando}
              disabled={!hayFiltro}
              onClick={() => void previsualizar('blacklist')}
            >
              Vetar TODO lo filtrado
            </Button>
          </Space>
        </div>

        {!hayFiltro && (
          <Alert
            style={{ marginTop: 12 }}
            type='info'
            showIcon
            message='Pon al menos un filtro para habilitar el borrado en masa'
            description='Así un clic accidental no puede vaciar la biblioteca entera.'
          />
        )}
      </Card>

      {/* ---------------------------------------------------------- tabla */}
      <Table<TrackRow>
        rowKey='id'
        size='small'
        loading={cargando}
        columns={columnas}
        dataSource={filas}
        scroll={{ x: 1100 }}
        rowSelection={{
          selectedRowKeys: seleccion,
          onChange: (keys) => setSeleccion(keys as number[]),
          preserveSelectedRowKeys: false,
        }}
        pagination={{
          current: pagina,
          pageSize: PAGINA,
          total,
          showSizeChanger: false,
          onChange: setPagina,
          showTotal: (t) => `${t.toLocaleString('es-ES')} canciones`,
        }}
      />

      {/* ---------------------------------------------------------- confirmación */}
      <Modal
        open={Boolean(confirmacion)}
        title={
          confirmacion?.accion === 'blacklist'
            ? '⚠️ Vetar en masa'
            : '⚠️ Borrado en masa'
        }
        okText={confirmacion?.accion === 'blacklist' ? 'Vetar ahora' : 'Borrar ahora'}
        okButtonProps={{ danger: true, loading: ejecutando }}
        cancelText='Cancelar'
        onOk={() => void ejecutarBulk()}
        onCancel={() => setConfirmacion(null)}
      >
        <Alert
          type='warning'
          showIcon
          style={{ marginBottom: 16 }}
          message={
            confirmacion?.accion === 'blacklist'
              ? `Se van a VETAR ${confirmacion?.afectadas.toLocaleString('es-ES')} canciones`
              : `Se van a BORRAR ${confirmacion?.afectadas.toLocaleString('es-ES')} canciones`
          }
          description={
            confirmacion?.accion === 'blacklist'
              ? 'No se borran los ficheros; solo se impide que se vuelvan a descargar.'
              : 'Se eliminan los ficheros del disco y las filas de la base de datos. No se puede deshacer.'
          }
        />
        <Title level={5}>Filtros aplicados</Title>
        <ul>
          {q.trim() && <li>Texto: <b>{q}</b></li>}
          {language && <li>Idioma: <b>{labelLang(language)}</b></li>}
          {genre && <li>Género: <b>{labelGenre(genre)}</b></li>}
          {artist && <li>Artista: <b>{artist}</b></li>}
          {status && <li>Estado: <b>{labelStatus(status)}</b></li>}
          {yearMin !== undefined && <li>Año desde: <b>{yearMin}</b></li>}
          {yearMax !== undefined && <li>Año hasta: <b>{yearMax}</b></li>}
        </ul>
        {confirmacion?.accion === 'delete' && (
          <Space>
            <Switch checked={vetoConfirmado} onChange={setVetoConfirmado} />
            <Text>
              Añadirlas a la lista negra para que <b>no se vuelvan a descargar</b>
            </Text>
          </Space>
        )}
      </Modal>
        </>
      )}
    </div>
  );
};

export default Library;
