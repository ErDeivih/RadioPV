/* eslint-disable jsx-a11y/alt-text */
import { Col, message, Modal, Row } from 'antd';
import { memo, useCallback, useEffect, useRef, useState } from 'react';
import ProForm, { ProFormText, ProFormTextArea } from '@ant-design/pro-form';

// Redux
import { api } from '../../store/api';
import { refreshPlaylist } from '../../store/slices/playlist';
import { useAppDispatch, useAppSelector } from '../../store/store';
import { yourLibraryActions } from '../../store/slices/yourLibrary';
import { editPlaylistModalActions } from '../../store/slices/editPlaylistModal';

// Utils
import { useTranslation } from 'react-i18next';

// Services
import { playlistService } from '../../services/playlists';

// Constants
import { PLAYLIST_DEFAULT_IMAGE } from '../../constants/spotify';

// Interfaces
import type { FormInstance } from 'antd/lib';

// Lado de la portada que se sube. La lista se pinta como mucho a ~640 px, así que mandar la foto
// original de la cámara (5-10 MB) por Tailscale es tirar datos y tiempo: se recorta cuadrada y se
// reescala aquí, en el móvil, antes de subirla.
const LADO_PORTADA = 640;

/**
 * Recorta la imagen a un cuadrado centrado, la reescala a 640 px y la devuelve en JPEG.
 * Se hace con un lienzo (canvas) del navegador: no hace falta ninguna librería.
 */
const recortarCuadrada = (file: File): Promise<{ base64: string; contentType: string }> =>
  new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const imagen = new Image();
    imagen.onload = () => {
      try {
        const lado = Math.min(imagen.width, imagen.height);
        const lienzo = document.createElement('canvas');
        lienzo.width = LADO_PORTADA;
        lienzo.height = LADO_PORTADA;
        const ctx = lienzo.getContext('2d');
        if (!ctx) throw new Error('El navegador no ha dado un lienzo');
        ctx.drawImage(
          imagen,
          (imagen.width - lado) / 2,
          (imagen.height - lado) / 2,
          lado,
          lado,
          0,
          0,
          LADO_PORTADA,
          LADO_PORTADA
        );
        const dataUrl = lienzo.toDataURL('image/jpeg', 0.88);
        resolve({ base64: dataUrl.split(',')[1], contentType: 'image/jpeg' });
      } catch (e) {
        reject(e);
      } finally {
        URL.revokeObjectURL(url);
      }
    };
    imagen.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('No se ha podido leer la imagen'));
    };
    imagen.src = url;
  });

export const EditPlaylistModal = memo(() => {
  const dispatch = useAppDispatch();
  const formRef = useRef<FormInstance>(null);
  const { t } = useTranslation(['playlist']);
  const playlist = useAppSelector((state) => state.editPlaylistModal.playlist);

  const [file, setFile] = useState<File>();
  const [fileUrl, setFileUrl] = useState<string>();
  // Si se ha pulsado «quitar foto»: la vista previa vuelve al relleno aunque la lista todavía
  // tenga portada en el servidor (el borrado se manda al guardar, igual que el nombre).
  const [sinFoto, setSinFoto] = useState(false);
  const [loading, setLoading] = useState<boolean>(false);

  function handleChange(e: any) {
    if (!e.target.files.length) {
      setFileUrl('');
      setFile(undefined);
      return;
    }
    const url = URL.createObjectURL(e.target.files[0]);
    setFileUrl(url);
    setFile(e.target.files[0]);
    setSinFoto(false);
  }

  useEffect(() => {
    if (playlist) {
      formRef.current?.setFieldsValue({
        name: playlist.name,
        description: playlist.description,
      });
    }
  }, [playlist]);

  // Al abrir otra lista (o la misma de nuevo) no debe arrastrarse la foto elegida antes.
  useEffect(() => {
    setFile(undefined);
    setFileUrl(undefined);
    setSinFoto(false);
  }, [playlist?.id]);

  const onClose = useCallback(() => {
    dispatch(editPlaylistModalActions.setPlaylist({ playlist: null }));
  }, [dispatch]);

  const refrescarPantalla = useCallback(() => {
    dispatch(yourLibraryActions.fetchMyPlaylists());
    if (!playlist) return;
    // Dos capas de caché que hay que tirar a la vez, o la pantalla sigue con el nombre viejo:
    //  1) la consulta de RTK Query de la página de la lista (`getPlaylistPage`), que es la que
    //     pinta el encabezado;
    //  2) el slice de la lista, que es lo que leen los componentes de dentro.
    dispatch(api.util.invalidateTags([{ type: 'Playlist', id: playlist.id }]));
    dispatch(refreshPlaylist(playlist.id));
  }, [dispatch, playlist]);

  const portadaActual = sinFoto
    ? PLAYLIST_DEFAULT_IMAGE
    : fileUrl
    ? fileUrl
    : playlist?.images && playlist.images.length
    ? playlist.images[0].url
    : PLAYLIST_DEFAULT_IMAGE;

  return (
    <>
      <Modal
        centered
        width={550}
        footer={null}
        open={!!playlist}
        onCancel={() => onClose()}
        title={
          <h1
            style={{
              fontWeight: 700,
              fontSize: '1.5rem',
              marginBlockStart: 0,
              paddingBlockEnd: 8,
              color: 'white',
            }}
          >
            {t('Edit details')}
          </h1>
        }
      >
        <ProForm
          formRef={formRef}
          style={{ marginTop: 10 }}
          onFinish={async (values) => {
            try {
              setLoading(true);
              const promesas: Promise<unknown>[] = [
                playlistService.changePlaylistDetails(playlist!.id, values),
              ];
              if (file) {
                try {
                  const { base64, contentType } = await recortarCuadrada(file);
                  promesas.push(
                    playlistService.changePlaylistImage(playlist!.id, base64, contentType)
                  );
                } catch {
                  message.error(t('Could not read that image'));
                }
              } else if (sinFoto) {
                promesas.push(playlistService.removePlaylistImage(playlist!.id));
              }
              await Promise.all(promesas);
              message.success(t('Playlist updated successfully'));
              setLoading(false);
              refrescarPantalla();
              dispatch(editPlaylistModalActions.setPlaylist({ playlist: null }));
              return true;
            } catch (error) {
              setLoading(false);
              message.error(t('Failed to update playlist'));
              return false;
            }
          }}
          submitter={{
            render: (props) => (
              <div>
                <div
                  style={{
                    display: 'flex',
                    gap: 12,
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  {/* Quitar la portada solo tiene sentido si la lista tiene una propia. */}
                  {playlist?.images?.[0]?.url && playlist.images[0].url !== PLAYLIST_DEFAULT_IMAGE ? (
                    <button
                      type='button'
                      className='edit-playlist-submit-button'
                      style={{ background: 'transparent', color: '#b3b3b3' }}
                      onClick={() => {
                        // No se borra aquí: se marca y se borra al guardar, igual que el nombre.
                        // Si el usuario se arrepiente, cerrar el diálogo no ha cambiado nada.
                        setFile(undefined);
                        setFileUrl(undefined);
                        setSinFoto(true);
                      }}
                    >
                      <span>{t('Remove photo')}</span>
                    </button>
                  ) : (
                    <span />
                  )}
                  <button
                    type='button'
                    disabled={loading}
                    className='edit-playlist-submit-button'
                    onClick={props.submit || props.onSubmit}
                  >
                    <span>{loading ? t('Saving…') : t('Save')}</span>
                  </button>
                </div>
              </div>
            ),
          }}
        >
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <div className='playlist-img-container'>
                <div className='playlist-img-overlay'>
                  <div className='playlist-img-overlay-container'>
                    <button type='button' aria-haspopup='true'>
                      <div className='icon'>
                        <svg
                          data-encore-id='icon'
                          role='img'
                          height={50}
                          width={50}
                          aria-hidden='true'
                          viewBox='0 0 24 24'
                          style={{ margin: '0 auto' }}
                        >
                          <path d='M17.318 1.975a3.329 3.329 0 1 1 4.707 4.707L8.451 20.256c-.49.49-1.082.867-1.735 1.103L2.34 22.94a1 1 0 0 1-1.28-1.28l1.581-4.376a4.726 4.726 0 0 1 1.103-1.735L17.318 1.975zm3.293 1.414a1.329 1.329 0 0 0-1.88 0L5.159 16.963c-.283.283-.5.624-.636 1l-.857 2.372 2.371-.857a2.726 2.726 0 0 0 1.001-.636L20.611 5.268a1.329 1.329 0 0 0 0-1.879z'></path>
                        </svg>
                        <span data-encore-id='text'>{t('Choose photo')}</span>
                      </div>
                    </button>
                    {/* El `accept` estaba mal escrito (`image/.jpg`): algunos móviles mostraban
                        la galería entera o directamente no dejaban elegir nada. */}
                    <input
                      type='file'
                      onChange={handleChange}
                      accept='image/jpeg,image/png,image/webp'
                    />
                  </div>
                </div>
                <img src={portadaActual} alt='' className='playlist-img' />
              </div>
            </Col>
            <Col span={16}>
              <ProFormText
                placeholder={t('Add a name')}
                name={'name'}
                rules={[{ required: true, message: '' }]}
              />
              <ProFormTextArea
                name={'description'}
                placeholder={t('Add an optional description')}
                fieldProps={{ autoSize: { minRows: 4 } }}
              />
            </Col>
          </Row>
        </ProForm>
      </Modal>
    </>
  );
});

EditPlaylistModal.displayName = 'EditPlaylistModal';
