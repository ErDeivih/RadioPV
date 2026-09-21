import { useParams, Link } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../../../store/store';
import { FC, RefObject, useEffect } from 'react';
import { profileActions } from '../../../store/slices/profile';
import ProfileContainer from './container';

interface ProfilePageProps {
  container: RefObject<HTMLDivElement | null>;
}

export const Profile: FC<ProfilePageProps> = (props) => {
  const dispatch = useAppDispatch();
  const params = useParams<{ userId: string }>();
  const user = useAppSelector((state) => state.profile.user);
  const loading = useAppSelector((state) => state.profile.loading);
  const notFound = useAppSelector((state) => state.profile.notFound);

  useEffect(() => {
    if (params.userId) dispatch(profileActions.fetchUser(params.userId));
    return () => {
      dispatch(profileActions.removeUser());
    };
  }, [dispatch, params.userId]);

  // Antes esto era `if (!user) return null`: una pantalla COMPLETAMENTE en blanco, sin decir si
  // estaba cargando o si ese perfil no existe (pasaba al abrir `/users/1`, un id que ya no está, o
  // al pedir el perfil de otra persona, que la API no sirve). En el móvil parecía que la aplicación
  // se había roto.
  if (notFound) {
    return (
      <div className='playlist-list'>
        <p className='empty-state'>
          Ese perfil no existe (o no se puede ver desde aquí).
          <br />
          <Link to='/'>Volver a la portada</Link>
        </p>
      </div>
    );
  }

  if (loading || !user) {
    return (
      <div className='playlist-list'>
        <p className='empty-state'>Cargando el perfil…</p>
      </div>
    );
  }

  return <ProfileContainer container={props.container} />;
};

export default Profile;
