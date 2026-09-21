import { FC, RefObject, useEffect, useRef, useState } from 'react';
import { useAppSelector } from '../../../../store/store';
import { DEFAULT_PAGE_COLOR } from '../../../../constants/spotify';
import UserHoverableMenu from './scrollHoverable';
import { getImageAnalysis2 } from '../../../../utils/imageAnyliser';
import tinycolor from 'tinycolor2';
import { UserHeader } from './header';
import { MyArtistsSection } from '../components/artists';
import { MyPlaylistsSection } from '../components/playlists';
import { Songs } from '../components/songs';

interface ProfilePageProps {
  container: RefObject<HTMLDivElement | null>;
}

export const ProfileContainer: FC<ProfilePageProps> = (props) => {
  const user = useAppSelector((state) => state.profile.user);
  const artists = useAppSelector((state) => state.profile.artists);
  const songs = useAppSelector((state) => state.profile.songs);
  const playlists = useAppSelector((state) => state.profile.playlists);

  const ref = useRef<HTMLDivElement>(null);
  const [color, setColor] = useState<string>(DEFAULT_PAGE_COLOR);

  // Las tres secciones (artistas, canciones y listas) devuelven `null` cuando están vacías, así que
  // un perfil sin datos era una cabecera y **un bloque gris enorme y mudo**. Se dice lo que pasa.
  const vacio = !artists?.length && !songs?.length && !playlists?.length;

  useEffect(() => {
    if (user && user.images?.length) {
      getImageAnalysis2(user.images[0].url).then((c) => {
        const color = tinycolor(c);
        while (color.isLight()) color.darken(10);
        setColor(color.darken(20).toString());
      });
    }
  }, [setColor, user]);

  return (
    <div className='Profile-section' ref={ref}>
      <UserHoverableMenu color={color} container={props.container} sectionContainer={ref} />
      <UserHeader color={color} />

      <div
        style={{
          maxHeight: 323,
          padding: '20px 15px',
          background: `linear-gradient(${color} -50%, ${DEFAULT_PAGE_COLOR} 90%)`,
        }}
      >
        <MyArtistsSection />

        <Songs />

        <MyPlaylistsSection />

        {vacio ? (
          <p className='empty-state'>
            Aquí aparecerá tu música: los artistas que más escuchas, tus listas públicas y lo más
            escuchado del mes. Todavía no hay nada que enseñar.
          </p>
        ) : null}
      </div>
    </div>
  );
};

export default ProfileContainer;
