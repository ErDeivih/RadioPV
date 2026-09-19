import { FC } from 'react';
import { Result, Tabs, Typography } from 'antd';
import { useAppSelector } from '../../store/store';
import Library from './Library';
import Blacklist from './Blacklist';
import Ingest from './Ingest';

const { Title, Paragraph } = Typography;

/**
 * Administración de RadioPV.
 *
 * Reúne en un solo sitio lo que antes solo se podía hacer desde la interfaz Streamlit:
 * gestionar la biblioteca, la lista negra y el interruptor de ingesta.
 *
 * Solo visible para usuarios con `is_admin`.
 */
export const Admin: FC = () => {
  const user = useAppSelector((state) => state.auth.user);

  // `is_admin` viaja en `/auth/me` y el adaptador lo copia al usuario de la interfaz. Antes se
  // perdía por el camino, así que esta comprobación era **siempre falsa**: el panel contestaba 403
  // a todo el mundo, incluido el administrador de verdad. Toda la gestión de la biblioteca (los
  // atajos de limpieza, el borrado en masa, la lista negra) era inalcanzable desde la interfaz.
  const esAdmin = Boolean(user?.is_admin);

  if (!user) return null;

  if (!esAdmin) {
    return (
      <Result
        status='403'
        title='403'
        subTitle='Esta sección es solo para administradores.'
      />
    );
  }

  return (
    <div style={{ padding: '8px 0 40px' }}>
      <div style={{ padding: '0 16px' }}>
        <Title level={2} style={{ marginBottom: 4 }}>
          Administración
        </Title>
        <Paragraph type='secondary' style={{ marginBottom: 0 }}>
          Gestiona la biblioteca, la lista negra y la ingesta del recolector.
        </Paragraph>
      </div>

      <Tabs
        defaultActiveKey='library'
        destroyInactiveTabPane
        items={[
          {
            key: 'library',
            label: '🎵 Biblioteca',
            children: <Library />,
          },
          {
            key: 'blacklist',
            label: '🚫 Lista negra',
            children: <Blacklist />,
          },
          {
            key: 'ingest',
            label: '🎛️ Ingesta',
            children: <Ingest />,
          },
        ]}
      />
    </div>
  );
};

export default Admin;
