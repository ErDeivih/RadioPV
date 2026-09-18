import { Col } from 'antd';
import { memo, type Dispatch, type SetStateAction } from 'react';

import { FavouriteArtists } from '../../components/favouriteArtists';
import { FeaturePlaylists } from '../../components/featurePlaylists';
import { HechoParaTi } from '../../components/mixes';
import { MadeForYou } from '../../components/madeForYou';
import { MoreLikeArtistSection } from '../../components/moreLikeArtists/MoreLikeArtistSection';
import { NewReleases } from '../../components/newReleases';
import { RecentlyPlayed } from '../../components/recentlyPlayed';
import { Rankings } from '../../components/rankings';
import { TopMixes } from '../../components/topMixes';
import { Tendencias } from '../../components/tendencias';
import { Estadisticas } from '../../components/estadisticas';
import { Trending } from '../../components/trending';
import { YourPlaylists } from '../../components/yourPlaylists';
import { useAppSelector } from '../../../../store/store';

interface HomeAllMusicSectionProps {
  setColor: Dispatch<SetStateAction<string>>;
}

const MoreLikeArtistCol = memo(({ index }: { index: number }) => {
  const user = useAppSelector((state) => !!state.auth.user);
  const section = useAppSelector((state) => state.home.moreLikeArtists[index]);

  if (!user || !section) {
    return null;
  }

  return (
    <Col span={24}>
      <MoreLikeArtistSection section={section} />
    </Col>
  );
});

export const HomeAllMusicSection = memo((_props: HomeAllMusicSectionProps) => {
  const user = useAppSelector((state) => !!state.auth.user);
  const section = useAppSelector((state) => state.home.section);
  const madeForYou = useAppSelector((state) => state.home.madeForYou);
  const recentlyPlayed = useAppSelector((state) => state.home.recentlyPlayed);

  const hasMadeForYou = !!madeForYou?.length;
  const hasRecentlyPlayed = !!recentlyPlayed?.length;
  const hasTopMixes = !!madeForYou?.some((p) => p.name?.toLowerCase().includes('mix'));

  return (
    <>
      {/* NOTA: aquí estaba `TopTracks`, la sección «Para ti» con DOCE CANCIONES SUELTAS, y era lo
       * primero que veía un usuario con sesión. Se ha quitado: la música se escucha en listas, y
       * lo que ofrece la portada son listas (los mixes, las que genera la aplicación y las tuyas).
       * Las recomendaciones personalizadas no se pierden: son justo el contenido de los mixes de
       * «Hecho para ti» y de la radio de cada canción. */}

      {user ? (
        <Col span={24}>
          <HechoParaTi />
        </Col>
      ) : null}

      {/* Las listas del usuario van arriba, no al final: incluyen las que genera la aplicación
       * para él ("Tus más escuchadas", "Descubrimientos de la semana"). */}
      {user ? (
        <Col span={24}>
          <YourPlaylists />
        </Col>
      ) : null}

      {/* «Estadisticas» TAMBIÉN eran canciones sueltas, no cifras: pinta «China — Anuel AA 2.4B ·
       * Thunderstruck — AC/DC 1.8B…», o sea una lista de canciones con sus reproducciones. Se
       * quita por lo mismo que «Tendencias»: la portada ofrece listas, y esa información (los
       * éxitos por popularidad) ya está en las listas generadas «Viral / Tendencia» y «Top…». */}

      {user && hasMadeForYou ? (
        <Col span={24}>
          <MadeForYou />
        </Col>
      ) : null}

      {user && section === 'ALL' && hasRecentlyPlayed ? (
        <Col span={24}>
          <RecentlyPlayed />
        </Col>
      ) : null}

      {user && hasTopMixes ? (
        <Col span={24}>
          <TopMixes />
        </Col>
      ) : null}

      <MoreLikeArtistCol index={0} />

      <MoreLikeArtistCol index={1} />

      <Col span={24}>
        <FeaturePlaylists />
      </Col>

      <MoreLikeArtistCol index={2} />

      <Col span={24}>
        <NewReleases />
      </Col>

      {!user || section === 'MUSIC' ? (
        <Col span={24}>
          <Rankings />
        </Col>
      ) : null}

      <MoreLikeArtistCol index={3} />

      {!user || section === 'MUSIC' ? (
        <Col span={24}>
          <Trending />
        </Col>
      ) : null}

      {user && section === 'ALL' ? (
        <Col span={24}>
          <FavouriteArtists />
        </Col>
      ) : null}
    </>
  );
});
