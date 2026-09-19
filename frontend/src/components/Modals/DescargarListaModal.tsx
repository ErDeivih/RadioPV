import { FC, useState } from 'react';
import { Button, Modal, Progress, Space, Typography, message } from 'antd';
import {
  descargarCanciones,
  elegirCarpeta,
  nombreDeFichero,
  puedeElegirCarpeta,
  type Progreso,
} from '../../services/descargas';

const { Text, Paragraph } = Typography;

interface Props {
  abierto: boolean;
  onCerrar: () => void;
  /** Nombre de lo que se descarga (una lista, un álbum…), para el mensaje. */
  nombre: string;
  canciones: { id: string; artista: string; titulo: string }[];
}

/**
 * Diálogo para descargar una lista entera a una carpeta.
 *
 * Se elige la carpeta ANTES de empezar cuando el navegador lo permite (Chrome y Edge de
 * escritorio): así los ficheros van directamente donde el usuario quiere, con el nombre
 * «Artista - Título.mp3», y sirven para cargar unos auriculares o una tarjeta sin más pasos.
 * En el móvil los navegadores no dejan elegir carpeta, así que se avisa y se descarga al
 * almacenamiento del navegador: mejor decirlo que dejar que parezca que no funciona.
 */
export const DescargarListaModal: FC<Props> = ({ abierto, onCerrar, nombre, canciones }) => {
  const [trabajando, setTrabajando] = useState(false);
  const [progreso, setProgreso] = useState<Progreso | null>(null);
  const puede = puedeElegirCarpeta();

  const empezar = async () => {
    let carpeta = null;
    if (puede) {
      carpeta = await elegirCarpeta();
      if (!carpeta) {
        // Cancelar la elección de carpeta no es un error: se sale sin decir nada.
        return;
      }
    }
    setTrabajando(true);
    setProgreso({ hechas: 0, total: canciones.length, actual: '', fallos: 0 });
    try {
      const r = await descargarCanciones(canciones, carpeta, setProgreso);
      if (r.fallos === 0) {
        message.success(`Descargadas ${r.hechas} canciones de «${nombre}»`);
      } else {
        message.warning(
          `Descargadas ${r.hechas} de ${r.total}; ${r.fallos} no se pudieron bajar`
        );
      }
    } catch {
      message.error('La descarga falló');
    } finally {
      setTrabajando(false);
    }
  };

  return (
    <Modal
      open={abierto}
      onCancel={onCerrar}
      title={`Descargar «${nombre}»`}
      footer={null}
      centered
    >
      <Paragraph type='secondary'>
        {canciones.length} canciones. Se guardan como <b>Artista - Título.mp3</b>.
      </Paragraph>

      {puede ? (
        <Paragraph>
          Se te pedirá <b>la carpeta donde guardarlas</b>. Ideal para cargar los auriculares o una
          tarjeta de memoria.
        </Paragraph>
      ) : (
        <Paragraph type='warning'>
          Este navegador no deja elegir carpeta (en el móvil no se puede). Los ficheros se
          descargarán a la carpeta de <b>Descargas</b> del dispositivo.
        </Paragraph>
      )}

      {progreso && (
        <div style={{ marginTop: 12 }}>
          <Progress
            percent={Math.round((progreso.hechas / Math.max(progreso.total, 1)) * 100)}
            status={trabajando ? 'active' : 'success'}
          />
          <Text type='secondary' style={{ fontSize: 12 }}>
            {progreso.hechas}/{progreso.total}
            {progreso.actual ? ` · ${progreso.actual}` : ''}
            {progreso.fallos ? ` · ${progreso.fallos} con error` : ''}
          </Text>
        </div>
      )}

      <Space style={{ marginTop: 16 }}>
        <Button type='primary' loading={trabajando} onClick={() => void empezar()}>
          {puede ? 'Elegir carpeta y descargar' : 'Descargar'}
        </Button>
        <Button onClick={onCerrar} disabled={trabajando}>
          Cerrar
        </Button>
      </Space>
    </Modal>
  );
};

export { nombreDeFichero };
