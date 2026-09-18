import { FC, memo, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaLock, FaUnlock } from 'react-icons/fa6';
import { Dropdown, MenuProps, message, Modal } from 'antd';
import { DeleteIcon, AddToQueueIcon, EditIcon, AddedToLibrary, AddToLibrary } from '../Icons';

// Services
import { userService } from '../../services/users';
import { playerService } from '../../services/player';
import { playlistService } from '../../services/playlists';

// Utils
import { useTranslation } from 'react-i18next';

// Interface
import type { Playlist } from '../../interfaces/playlists';

// Redux
import { uiActions } from '../../store/slices/ui';
import { fetchQueue } from '../../store/slices/queue';
import { useAppDispatch, useAppSelector } from '../../store/store';
import { yourLibraryActions } from '../../store/slices/yourLibrary';
import { editPlaylistModalActions } from '../../store/slices/editPlaylistModal';

interface PlayistActionsWrapperProps {
  playlist: Playlist;
  isCurrent?: boolean;
  onRefresh?: () => void;
  trigger?: ('contextMenu' | 'click')[];
  children: React.ReactNode | React.ReactNode[];
}

export const PlayistActionsWrapper: FC<PlayistActionsWrapperProps> = memo((props) => {
  const { children, playlist } = props;

  const { t } = useTranslation(['playlist']);
  // `Modal.confirm` estático: funciona gracias al puente de React 19 de `index.tsx`.
  const [modal, contextoModal] = Modal.useModal();

  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const userId = useAppSelector((state) => state.auth.user?.id);
  const myPlaylists = useAppSelector((state) => state.yourLibrary.myPlaylists);
  const canEdit = useMemo(() => userId === playlist.owner?.id, [userId, playlist.owner?.id]);

  const handleUserValidation = useCallback(
    (button?: boolean) => {
      if (!userId) {
        dispatch(button ? uiActions.openLoginButton() : uiActions.openLoginTooltip());
        return false;
      }
      return true;
    },
    [dispatch, userId]
  );

  const inLibrary = useMemo(() => {
    return myPlaylists.some((p) => p.id === playlist.id);
  }, [myPlaylists, playlist.id]);

  const items = useMemo(() => {
    const items: MenuProps['items'] = [];

    if (canEdit) {
      items.push(
        {
          label: t('Edit details'),
          key: 1,
          icon: <EditIcon />,
          onClick: () => {
            if (!handleUserValidation()) return;
            dispatch(editPlaylistModalActions.setPlaylist({ playlist }));
          },
        },
        {
          label: t('Delete playlist'),
          key: '2',
          icon: <DeleteIcon />,
          onClick: () => {
            if (!handleUserValidation()) return;
            // Confirmación ANTES de borrar. Antes se borraba directamente al tocar la opción del
            // menú: en el móvil, un toque de más en una lista con su nombre y su foto la borraba
            // sin preguntar y sin vuelta atrás.
            modal.confirm({
              title: t('Delete playlist question'),
              content: t('This cannot be undone'),
              okText: t('Delete'),
              okButtonProps: { danger: true },
              cancelText: t('Cancel'),
              centered: true,
              onOk: () =>
                playlistService.deletePlaylist(playlist.id).then(() => {
                  message.open({ type: 'success', content: t('Playlist deleted') });
                  navigate('/library');
                }),
            });
          },
        },
        {
          type: 'divider',
        }
      );

      if (playlist.public) {
        items.push({
          label: t('Make private'),
          key: 4,
          icon: <FaLock size={16} fill='#bababa' style={{ padding: 0, marginInlineEnd: 0 }} />,
          onClick: () => {
            if (!handleUserValidation()) return;
            return playlistService
              .changePlaylistDetails(playlist.id, { public: false })
              .then(() => {
                props.onRefresh?.();
                message.open({
                  type: 'success',
                  content: t('Playlist is now private'),
                });
              });
          },
        });
      } else {
        items.push({
          label: t('Make public'),
          key: 5,
          icon: <FaUnlock size={16} fill='#bababa' style={{ padding: 0, marginInlineEnd: 0 }} />,
          onClick: () => {
            if (!handleUserValidation()) return;
            return playlistService
              .changePlaylistDetails(playlist.id, { public: true, collaborative: false })
              .then(() => {
                props.onRefresh?.();
                message.open({
                  type: 'success',
                  content: t('Playlist is now public'),
                });
              });
          },
        });
      }
    } else {
      if (inLibrary) {
        items.push(
          {
            label: t('Remove from Your Library'),
            key: 9,
            icon: <AddedToLibrary style={{ height: 16, width: 16, marginInlineEnd: 0 }} />,
            onClick: () => {
              if (!handleUserValidation()) return;
              return userService.unfollowPlaylist(playlist.id).then(() => {
                dispatch(yourLibraryActions.fetchMyPlaylists());
                message.open({
                  type: 'success',
                  content: t('Removed from Your Library'),
                });
              });
            },
          },
          {
            type: 'divider',
          }
        );
      } else {
        items.push(
          {
            label: t('Add to Your Library'),
            key: 8,
            icon: <AddToLibrary style={{ height: 16, width: 16, marginInlineEnd: 0 }} />,
            onClick: () => {
              if (!handleUserValidation(true)) return;
              return userService.followPlaylist(playlist.id).then(() => {
                dispatch(yourLibraryActions.fetchMyPlaylists());
                message.open({
                  type: 'success',
                  content: t('Saved to Your Library'),
                });
              });
            },
          },
          {
            type: 'divider',
          }
        );
      }
    }

    items.push({
      label: t('Add to queue'),
      key: '3',
      // Estaba `disabled: true` porque no funcionaba: se pasaba la URI de la playlist a
      // `addToQueue`, que la trataba como una canción suelta y pedía `/tracks/{id-playlist}`
      // (404). Ahora `addContextToQueue` resuelve todas las canciones de la lista.
      icon: <AddToQueueIcon />,
      onClick: () => {
        if (!handleUserValidation()) return;
        return playerService.addContextToQueue(playlist.uri).then((n) => {
          dispatch(fetchQueue());
          message.open({
            type: n ? 'success' : 'warning',
            content: n ? t('Added to queue') : t('No songs to add'),
          });
        });
      },
    });

    return items;
  }, [canEdit, dispatch, handleUserValidation, inLibrary, modal, navigate, playlist, props, t]);

  return (
    <>
      {contextoModal}
      <Dropdown menu={{ items }} trigger={props.trigger}>
        {children}
      </Dropdown>
    </>
  );
});
