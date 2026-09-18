import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
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
 * Atajos de limpieza: ponen los filtros de un toque para no tener que ir combinando
 * desplegables uno a uno. Cada uno lleva el recuento REAL que devuelve el servidor
 * (`facets.salud`), y ese número es exactamente lo que se borraría.
 *
 * `vetar` va aparte por un motivo: vetar impide que la canción vuelva a descargarse nunca.
 *  · Para lo que está roto (sin fichero, perdida, fallida, en cuarentena) vetar es lo correcto:
 *    si no, el recolector la vuelve a bajar y vuelve a quedar rota.
 *  · Para lo que simplemente no te gusta (poco conocida, sin idioma) vetar NO toca: si algún
 *    día la quieres, tienes que poder recuperarla.
 */
interface Atajo {
  clave: string;
  etiqueta: string;
  porque: string;
  filtros: Partial<TrackFilters>;
  n: (f: Facets) => number;
  vetar: boolean;
}

const ATAJOS: Atajo[] = [
  {
    clave: 'sin-idioma',
    etiqueta: 'Sin idioma detectado',
    porque: 'No se ha podido saber en qué idioma cantan. La política es español, latino e inglés.',
    filtros: { language: 'other' },
    n: (f) => f.salud.sin_idioma.n,
    vetar: false,
  },
  {
    clave: 'cortas',
    etiqueta: 'Retales de menos de 1 minuto',
    porque: 'Recortes, fragmentos y adelantos. Rara vez es una canción entera.',
    filtros: { duration_max: 59 },
    n: (f) => f.salud.cortas.n,
    vetar: false,
  },
  {
    clave: 'sin-fichero',
    etiqueta: 'Filas sin fichero',
    porque: 'Están en la base pero no hay ningún fichero suyo en el disco.',
    filtros: { has_file_path: false },
    n: (f) => f.salud.sin_fichero.n,
    vetar: true,
  },
  {
    clave: 'perdidas',
    etiqueta: 'Perdidas',
    porque: 'El fichero existía y ha desaparecido. La comprobación diaria las marca así.',
    filtros: { status: 'perdida' },
    n: (f) => f.salud.perdidas.n,
    vetar: true,
  },
  {
    clave: 'cuarentena',
    etiqueta: 'En cuarentena',
    porque: 'No han pasado el control de calidad (audio o emparejamiento).',
    filtros: { status: 'cuarentena' },
    n: (f) => f.salud.cuarentena.n,
    vetar: true,
  },
  {
    clave: 'fallidas',
    etiqueta: 'Descargas fallidas',
    porque: 'La descarga no terminó bien.',
    filtros: { status: 'fallida' },
    n: (f) => f.salud.fallidas.n,
    vetar: true,
  },
  {
    clave: 'incompletas',
    etiqueta: 'Incompletas',
    porque: 'Se bajaron a medias.',
    filtros: { status: 'incompleta' },
    n: (f) => f.salud.incompletas.n,
    vetar: true,
  },
  {
    clave: 'peor-40',
    etiqueta: 'Peor valoradas (popularidad < 40)',
    porque: 'De las que menos suenan en el mundo. Solo entran las que TIENEN dato de popularidad.',
    filtros: { rank_max: 39 },
    n: (f) => f.salud.rank_bajo_40.n,
    vetar: false,
  },
  {
    clave: 'peor-60',
    etiqueta: 'Muy poco conocidas (< 60)',
    porque: 'Tramo más amplio que el anterior. Bueno para hacer sitio en el disco.',
    filtros: { rank_max: 59 },
    n: (f) => f.salud.rank_bajo_60.n,
    vetar: false,
  },
];

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
  /** Último atajo pulsado, para poder marcarlo como activo. */
  const [atajoActivo, setAtajoActivo] = useState<string | null>(null);

  // Filtros
  const [q, setQ] = useState('');
  const [language, setLanguage] = useState<string | undefined>();
  const [genre, setGenre] = useState<string | undefined>();
  const [artist, setArtist] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [yearMin, setYearMin] = useState<number | undefined>();
  const [yearMax, setYearMax] = useState<number | undefined>();

  // Filtros avanzados («Más filtros»): para que no se escape nada
  const [era, setEra] = useState<string | undefined>();
  const [explicit, setExplicit] = useState<boolean | undefined>();
  const [isRemix, setIsRemix] = useState<boolean | undefined>();
  const [huerfanas, setHuerfanas] = useState(false);
  const [rankMin, setRankMin] = useState<number | undefined>();
  const [rankMax, setRankMax] = useState<number | undefined>();
  const [durMin, setDurMin] = useState<number | undefined>();
  const [durMax, setDurMax] = useState<number | undefined>();
  const [bpmMin, setBpmMin] = useState<number | undefined>();
  const [bpmMax, setBpmMax] = useState<number | undefined>();
  const [energyMin, setEnergyMin] = useState<number | undefined>();
  const [energyMax, setEnergyMax] = useState<number | undefined>();
  const [matchMin, setMatchMin] = useState<number | undefined>();

  // Vista: lista plana de canciones, o agrupada (por artista, álbum, género, idioma, año)
  const [vista, setVista] = useState<'tracks' | GroupBy>('tracks');

  // Confirmación del borrado en masa
  const [confirmacion, setConfirmacion] = useState<{
    afectadas: number;
    accion: 'delete' | 'blacklist';
  } | null>(null);
  const [vetoConfirmado, setVetoConfirmado] = useState(true);
  const [ejecutando, setEjecutando] = useState(false);

  /** Filtros en el formato que espera la API. Mismo juego que el borrado en masa. */
  const filtros = useMemo<TrackFilters>(
    () => ({
      q: q.trim() || undefined,
      language,
      genre,
      artist,
      status,
      year_min: yearMin,
      year_max: yearMax,
      era,
      explicit,
      is_remix: isRemix,
      has_file_path: huerfanas ? false : undefined,
      rank_min: rankMin,
      rank_max: rankMax,
      duration_min: durMin,
      duration_max: durMax,
      bpm_min: bpmMin,
      bpm_max: bpmMax,
      energy_min: energyMin,
      energy_max: energyMax,
      match_score_min: matchMin,
    }),
    [
      q, language, genre, artist, status, yearMin, yearMax,
      era, explicit, isRemix, huerfanas, rankMin, rankMax,
      durMin, durMax, bpmMin, bpmMax, energyMin, energyMax, matchMin,
    ]
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
          yearMax !== undefined ||
          era ||
          explicit !== undefined ||
          isRemix !== undefined ||
          huerfanas ||
          rankMin !== undefined ||
          rankMax !== undefined ||
          durMin !== undefined ||
          durMax !== undefined ||
          bpmMin !== undefined ||
          bpmMax !== undefined ||
          energyMin !== undefined ||
          energyMax !== undefined ||
          matchMin !== undefined
      ),
    [
      q, language, genre, artist, status, yearMin, yearMax,
      era, explicit, isRemix, huerfanas, rankMin, rankMax,
      durMin, durMax, bpmMin, bpmMax, energyMin, energyMax, matchMin,
    ]
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
  }, [language, genre, artist, status, yearMin, yearMax, rankMax, durMin, durMax]);

  const limpiarFiltros = () => {
    setQ('');
    setLanguage(undefined);
    setGenre(undefined);
    setArtist(undefined);
    setStatus(undefined);
    setYearMin(undefined);
    setYearMax(undefined);
    setEra(undefined);
    setExplicit(undefined);
    setIsRemix(undefined);
    setHuerfanas(false);
    setRankMin(undefined);
    setRankMax(undefined);
    setDurMin(undefined);
    setDurMax(undefined);
    setBpmMin(undefined);
    setBpmMax(undefined);
    setEnergyMin(undefined);
    setEnergyMax(undefined);
    setMatchMin(undefined);
    setAtajoActivo(null);
  };

  /** Aplica un atajo: limpia lo anterior y deja puestos SOLO sus filtros. */
  const aplicarAtajo = (a: Atajo) => {
    limpiarFiltros();
    const f = a.filtros;
    if (f.q !== undefined) setQ(f.q);
    if (f.language !== undefined) setLanguage(f.language);
    if (f.genre !== undefined) setGenre(f.genre);
    if (f.artist !== undefined) setArtist(f.artist);
    if (f.status !== undefined) setStatus(f.status);
    if (f.era !== undefined) setEra(f.era);
    if (f.explicit !== undefined) setExplicit(f.explicit);
    if (f.is_remix !== undefined) setIsRemix(f.is_remix);
    if (f.has_file_path !== undefined) setHuerfanas(f.has_file_path === false);
    if (f.rank_min !== undefined) setRankMin(f.rank_min);
    if (f.rank_max !== undefined) setRankMax(f.rank_max);
    if (f.duration_min !== undefined) setDurMin(f.duration_min);
    if (f.duration_max !== undefined) setDurMax(f.duration_max);
    // El veto se pone según el tipo de atajo: ver la explicación en ATAJOS.
    setVetoPorDefecto(a.vetar);
    setAtajoActivo(a.clave);
    setPagina(1);
    setSeleccion([]);
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
      {/* ------------------------------------------------------ limpieza rápida */}
      <Card
        size='small'
        style={{ marginBottom: 16 }}
        title={<Text strong>Limpieza rápida</Text>}
        extra={
          <Text type='secondary' style={{ fontSize: 12 }}>
            Un toque pone los filtros · mira el número · luego «Borrar TODO lo filtrado»
          </Text>
        }
      >
        {!facets ? (
          <Text type='secondary'>Cargando recuentos…</Text>
        ) : (
          <Space wrap size={[8, 8]}>
            {ATAJOS.map((a) => {
              const n = a.n(facets);
              return (
                <Tooltip
                  key={a.clave}
                  title={
                    <>
                      {a.porque}
                      <br />
                      <b>
                        {a.vetar
                          ? 'Al borrar se vetará (no volverá a descargarse)'
                          : 'Al borrar NO se vetará: podrás recuperarla más adelante'}
                      </b>
                    </>
                  }
                >
                  <Button
                    size='small'
                    type={atajoActivo === a.clave ? 'primary' : 'default'}
                    disabled={n === 0}
                    onClick={() => aplicarAtajo(a)}
                  >
                    {a.etiqueta}{' '}
                    <Badge
                      count={n}
                      showZero
                      overflowCount={99999}
                      style={{
                        backgroundColor: n === 0 ? '#444' : atajoActivo === a.clave ? '#fff' : '#1677ff',
                        color: atajoActivo === a.clave ? '#1677ff' : '#fff',
                        fontSize: 11,
                      }}
                    />
                  </Button>
                </Tooltip>
              );
            })}
          </Space>
        )}
      </Card>

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

        <Collapse
          ghost
          size='small'
          style={{ marginTop: 4 }}
          items={[
            {
              key: 'mas',
              label: 'Más filtros (época, explícito, remixes, popularidad, duración, BPM, energía)',
              children: (
                <Row gutter={[8, 8]} align='middle'>
                  <Col xs={12} md={3}>
                    <Select
                      style={{ width: '100%' }}
                      placeholder='Época'
                      allowClear
                      value={era}
                      onChange={setEra}
                      options={opciones(facets?.eras)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <Select
                      style={{ width: '100%' }}
                      placeholder='Explícito'
                      allowClear
                      value={explicit}
                      onChange={setExplicit}
                      options={[
                        { value: true, label: 'Solo explícitas' },
                        { value: false, label: 'Solo limpias' },
                      ]}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <Select
                      style={{ width: '100%' }}
                      placeholder='Remixes'
                      allowClear
                      value={isRemix}
                      onChange={setIsRemix}
                      options={[
                        { value: true, label: 'Solo remixes' },
                        { value: false, label: 'Sin remixes' },
                      ]}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='Popularidad mín.'
                      value={rankMin}
                      onChange={(v) => setRankMin(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='Popularidad máx.'
                      value={rankMax}
                      onChange={(v) => setRankMax(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='Duración mín. (s)'
                      value={durMin}
                      onChange={(v) => setDurMin(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='Duración máx. (s)'
                      value={durMax}
                      onChange={(v) => setDurMax(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='BPM mín.'
                      value={bpmMin}
                      onChange={(v) => setBpmMin(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='BPM máx.'
                      value={bpmMax}
                      onChange={(v) => setBpmMax(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='Energía mín.'
                      value={energyMin}
                      onChange={(v) => setEnergyMin(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='Energía máx.'
                      value={energyMax}
                      onChange={(v) => setEnergyMax(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} md={3}>
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder='Calidad de match mín.'
                      value={matchMin}
                      onChange={(v) => setMatchMin(v ?? undefined)}
                    />
                  </Col>
                  <Col xs={24} md={9}>
                    <Space>
                      <Switch checked={huerfanas} onChange={setHuerfanas} size='small' />
                      <Text type={huerfanas ? 'danger' : 'secondary'}>
                        Solo huérfanas (filas sin fichero)
                        {facets?.booleanos ? ` · hay ${facets.booleanos.huerfanas.n}` : ''}
                      </Text>
                    </Space>
                  </Col>
                </Row>
              ),
            },
          ]}
        />
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
          {/* Los atajos de limpieza se apoyan en estos: si no se listaran, el aviso diría
              «se van a borrar 4.000 canciones» sin decir POR QUÉ. */}
          {era && <li>Época: <b>{era}</b></li>}
          {rankMin !== undefined && <li>Popularidad mínima: <b>{rankMin}</b></li>}
          {rankMax !== undefined && <li>Popularidad máxima: <b>{rankMax}</b></li>}
          {durMin !== undefined && <li>Duración mínima: <b>{durMin} s</b></li>}
          {durMax !== undefined && <li>Duración máxima: <b>{durMax} s</b></li>}
          {huerfanas && <li>Sin fichero: <b>sí</b></li>}
          {explicit !== undefined && <li>Explícitas: <b>{explicit ? 'sí' : 'no'}</b></li>}
          {isRemix !== undefined && <li>Remixes: <b>{isRemix ? 'sí' : 'no'}</b></li>}
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
