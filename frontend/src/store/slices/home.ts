import { createAsyncThunk, createSlice, PayloadAction } from '@reduxjs/toolkit';

// Services
import { albumsService } from '../../services/albums';
import { artistService } from '../../services/artist';
import { playerService } from '../../services/player';
import { playlistService } from '../../services/playlists';

// Interfaz
import axios from '../../axios';
import { toTrack, toPlaylist } from '../../api/adapt';
import type { TrackOut, PlaylistOut } from '../../api/types';

// Interfaces
import type { RootState } from '../store';
import type { Track } from '../../interfaces/track';
import type { Album } from '../../interfaces/albums';
import type { Artist } from '../../interfaces/artist';
import type { Playlist } from '../../interfaces/playlists';
import type { Episode } from '../../interfaces/episode';
import { categoriesService } from '../../services/categories';
import { searchEpisodes } from '../../services/search';
import { fetchMoreLikeArtistItems } from '../../pages/Home/utils/fetchMoreLikeArtistItems';

// Utils
import { groupBy, uniq, uniqBy } from 'lodash';

// Constants
import {
  MADE_FOR_YOU_URI,
  PODCAST_SEARCH_MIGHT_LIKE_QUERY,
  PODCAST_SEARCH_TO_TRY_QUERY,
  RANKING_URI,
  TRENDING_URI,
} from '../../constants/spotify';

export interface MoreLikeArtistSection {
  artist: Artist;
  items: Awaited<ReturnType<typeof fetchMoreLikeArtistItems>>;
}

/** P · un tema en las tendencias de popularidad (GET /stats/popularidad). */
export interface PopularidadItem {
  track_id: number;
  title: string;
  artist: string;
  genre?: string | null;
  views?: number;
  popularidad?: number | null;
  variacion?: number | null;
}

/** P · estadísticas agregadas de popularidad (GET /stats/popularidad). */
export interface PopularidadStats {
  top_views: PopularidadItem[];
  top_score: PopularidadItem[];
  por_genero: { genero: string; media_pop: number; n: number }[];
  total_popular: number;
}


const initialState: {
  topTracks: Track[];
  newReleases: Album[];
  madeForYou: Playlist[];
  featurePlaylists: Playlist[];
  rankings: Playlist[];
  trending: Playlist[];
  recentlyPlayed: (Track | Artist | Album)[];
  section: 'ALL' | 'MUSIC' | 'PODCAST';
  podcastFilter: 'PODCASTS' | 'FOLLOWING';
  episodesMightLike: Episode[];
  episodesToTry: Episode[];
  moreLikeArtists: MoreLikeArtistSection[];
  mixes: { kind: string; explicacion: string | null }[];
  popularidad: { subiendo: PopularidadItem[]; bajando: PopularidadItem[]; nuevas: PopularidadItem[] } | null;
  stats: PopularidadStats | null;
} = {
  trending: [],
  rankings: [],
  topTracks: [],
  section: 'ALL',
  podcastFilter: 'PODCASTS',
  madeForYou: [],
  newReleases: [],
  recentlyPlayed: [],
  featurePlaylists: [],
  episodesMightLike: [],
  episodesToTry: [],
  moreLikeArtists: [],
  mixes: [],
  popularidad: null,
  stats: null,
};

export const fetchMadeForYou = createAsyncThunk('home/fetchMadeForYou', async () => {
  const response = await categoriesService.fetchCategoryPlaylists(MADE_FOR_YOU_URI, { limit: 50 });
  return response.data.playlists.items;
});

export const fetchRanking = createAsyncThunk('home/fetchRanking', async () => {
  const response = await categoriesService.fetchCategoryPlaylists(RANKING_URI, { limit: 10 });
  return response.data.playlists.items;
});

export const fetchTrending = createAsyncThunk('home/fetchTrending', async () => {
  const response = await categoriesService.fetchCategoryPlaylists(TRENDING_URI, { limit: 10 });
  return response.data.playlists.items;
});

export const fetchNewReleases = createAsyncThunk('home/fetchNewReleases', async () => {
  const response = await albumsService.fetchNewRelases({ limit: 10 });
  return response.data.albums.items;
});

export const fetchTopTracks = createAsyncThunk('home/fetchTopTracks', async () => {
  // "Para ti": recomendaciones personalizadas (radio por perfil). El 👍 en la UI cambia esto al
  // recargar, porque el backend pondera likes/plays/skips con recencia.
  const { data } = await axios.get<TrackOut[]>('/recommend', { params: { n: 12 } });
  return data.map(toTrack);
});

/** U3 · "Hecho para ti": los mixes del usuario (kind, explicacion) desde GET /mixes. */
export const fetchMixes = createAsyncThunk('home/fetchMixes', async () => {
  const { data } = await axios.get<{ kind: string; explicacion: string | null; tracks_json: string }[]>('/mixes');
  return data;
});

/** P · tendencias + estadísticas de popularidad desde GET /stats/popularidad. */
export const fetchPopularidad = createAsyncThunk('home/fetchPopularidad', async () => {
  const { data } = await axios.get<{
    tendencias: { subiendo: PopularidadItem[]; bajando: PopularidadItem[]; nuevas: PopularidadItem[] };
    estadisticas: PopularidadStats;
  }>('/stats/popularidad');
  return data;
});

export const fetchRecentlyPlayed = createAsyncThunk('home/fetchRecentlyPlayed', async () => {
  try {
    const response = await playerService.getRecentlyPlayed({ limit: 50 });

    const items = response.items;

    const groupedItems = groupBy(
      items.filter((item) => ['artist', 'playlist', 'album'].includes(item.context?.type)),
      (item) => item.context.type,
    );

    const artistsTracks = groupedItems['artist'] || [];
    const albumsTracks = groupedItems['album'] || [];

    // Cap how many ids we resolve: batch endpoints were removed (Feb 2026), so each id is now an
    // individual GET. Resolving every unique id from 50 recently-played items could fire dozens of
    // requests and trip the rate limit; the row only shows a handful, so 8 each is plenty.
    const artistsIds = uniq(artistsTracks.map((item) => item.context.uri.split(':')[2])).slice(0, 8);
    const albumsIds = uniq(albumsTracks.map((item) => item.context.uri.split(':')[2])).slice(0, 8);

    const promises = [
      artistsIds.length
        ? artistService.fetchArtists(artistsIds)
        : Promise.resolve({ data: { artists: [] } }),
      albumsIds.length
        ? albumsService.fetchAlbums(albumsIds)
        : Promise.resolve({ data: { albums: [] } }),
    ];

    const [artistsResponse, albumsResponse] = await Promise.all(promises);

    // @ts-ignore
    const artists: Artist[] = artistsResponse.data.artists;

    // @ts-ignore
    const albums: Album[] = albumsResponse.data.albums;

    const tracks = items.map((item) => {
      if (item.context?.type === 'artist') {
        return artists.find((artist) => artist.id === item.context.uri.split(':')[2])!;
      }

      if (item.context?.type === 'album') {
        return albums.find((album) => album.id === item.context.uri.split(':')[2])!;
      }

      return item.track;
    });

    return uniqBy(tracks, 'id');
  } catch (error) {
    void error;   // A3: sin console.log suelto; el toast lo usa F5 en el interceptor
    return [];
  }
});

const normalizeSearchEpisodes = (items: Episode[] = []) =>
  items.filter((episode): episode is Episode => !!episode?.id && !!episode?.name && !!episode?.uri);

const pickUniqueEpisodes = (pools: Episode[][], countPerPool: number) => {
  const seen = new Set<string>();
  const pick = (pool: Episode[], count: number) => {
    const picked: Episode[] = [];
    for (const episode of pool) {
      if (picked.length >= count) break;
      if (seen.has(episode.id)) continue;
      seen.add(episode.id);
      picked.push(episode);
    }
    return picked;
  };

  const [mightLikePool, toTryPool, ...fallbackPools] = pools;
  const mightLike = pick(mightLikePool, countPerPool);
  let toTry = pick(toTryPool, countPerPool);

  if (toTry.length < countPerPool) {
    const fallback = fallbackPools.flat();
    toTry = [...toTry, ...pick(fallback, countPerPool - toTry.length)];
  }

  return { mightLike, toTry };
};

export const fetchPodcastEpisodes = createAsyncThunk('home/fetchPodcastEpisodes', async () => {
  const [mightLikeRes, toTryRes] = await Promise.all([
    searchEpisodes({ q: PODCAST_SEARCH_MIGHT_LIKE_QUERY, limit: 20 }),
    searchEpisodes({ q: PODCAST_SEARCH_TO_TRY_QUERY, limit: 20, offset: 5 }),
  ]);

  const mightLikePool = normalizeSearchEpisodes(mightLikeRes.data.episodes?.items);
  const toTryPool = normalizeSearchEpisodes(toTryRes.data.episodes?.items);
  const combinedFallback = uniqBy([...toTryPool, ...mightLikePool], 'id');

  return pickUniqueEpisodes([mightLikePool, toTryPool, combinedFallback], 1);
});

export const fetchMoreLikeArtists = createAsyncThunk('home/fetchMoreLikeArtists', async () => {
  // Disabled. This fanned out `GET /artists/{id}/albums` per followed artist on EVERY Home load,
  // which Spotify rate-limits *per endpoint* — that single endpoint was being driven into a 429
  // cooldown while every other endpoint stayed healthy. The section was already degraded anyway
  // (related-artists was removed from the API in Nov 2024 / Feb 2026, so it only showed the
  // artist's own albums + name-matched playlists). Returning [] stops the hammering and lets the
  // endpoint's rate-limit window recover. Re-enable via fetchMoreLikeArtistItems if quota allows.
  return [];
});

export const fecthFeaturedPlaylists = createAsyncThunk(
  'home/fecthFeaturedPlaylists',
  async (_, { getState }) => {
    const state = getState() as RootState;
    // Antes esto pedía "featured playlists" (una categoría), que en este servidor devolvía vacío:
    // la fila no se veía nunca. Ahora son LAS LISTAS QUE GENERA LA PROPIA APLICACIÓN (Novedades,
    // Fiesta, Clásicos, En español, Top pop, Top 2000s, Viral / Tendencia…), que es justo lo que
    // debe ofrecer la portada: listas, no canciones sueltas.
    if (!state.auth.user) return [];        // /playlists/system exige sesión
    const { data } = await axios.get<PlaylistOut[]>('/playlists/system');
    // Las listas de mashups/remixes, sesiones de DJ y tech house van PRIMERO. Antes se ordenaba sólo
    // por número de canciones, así que quedaban enterradas entre las demás (y «Sesiones de DJ», que
    // tiene menos porque hay menos sesiones grabadas, se caía de la fila): el tipo de música que el
    // usuario más escucha era el que peor se encontraba en la portada. El tech house lo pidió él
    // expresamente, así que va en ese grupo de cabeza.
    const PRIMERO = ['Tech house y guaracha', 'Mashups y remixes', 'Sesiones de DJ'];
    const sitio = (n?: string) => {
      const i = PRIMERO.indexOf(n ?? '');
      return i === -1 ? PRIMERO.length : i;
    };
    return [...data]
      .sort((a, b) => sitio(a.name) - sitio(b.name) || (b.n_tracks ?? 0) - (a.n_tracks ?? 0))
      .slice(0, 20)
      .map((p) => toPlaylist(p));
  },
);

const homeSlice = createSlice({
  name: 'home',
  initialState,
  reducers: {
    setSection(state, action: PayloadAction<'ALL' | 'MUSIC' | 'PODCAST'>) {
      state.section = action.payload;
      if (action.payload !== 'PODCAST') {
        state.podcastFilter = 'PODCASTS';
      }
    },
    setPodcastFilter(state, action: PayloadAction<'PODCASTS' | 'FOLLOWING'>) {
      state.podcastFilter = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder.addCase(fetchNewReleases.fulfilled, (state, action) => {
      state.newReleases = action.payload as any as any[];
    });
    builder.addCase(fetchTopTracks.fulfilled, (state, action) => {
      state.topTracks = action.payload;
    });
    builder.addCase(fecthFeaturedPlaylists.fulfilled, (state, action) => {
      state.featurePlaylists = action.payload;
    });
    builder.addCase(fetchMadeForYou.fulfilled, (state, action) => {
      state.madeForYou = action.payload;
    });
    builder.addCase(fetchRecentlyPlayed.fulfilled, (state, action) => {
      state.recentlyPlayed = action.payload;
    });
    builder.addCase(fetchRanking.fulfilled, (state, action) => {
      state.rankings = action.payload;
    });
    builder.addCase(fetchTrending.fulfilled, (state, action) => {
      state.trending = action.payload;
    });
    builder.addCase(fetchPodcastEpisodes.fulfilled, (state, action) => {
      state.episodesMightLike = action.payload.mightLike;
      state.episodesToTry = action.payload.toTry;
    });
    builder.addCase(fetchMoreLikeArtists.fulfilled, (state, action) => {
      state.moreLikeArtists = action.payload;
    });
    builder.addCase(fetchMixes.fulfilled, (state, action) => {
      state.mixes = action.payload;
    });
    builder.addCase(fetchPopularidad.fulfilled, (state, action) => {
      state.popularidad = action.payload.tendencias;
      state.stats = action.payload.estadisticas;
    });
  },
});

export const homeActions = {
  ...homeSlice.actions,
  fetchRanking,
  fetchTrending,
  fetchTopTracks,
  fetchMadeForYou,
  fetchNewReleases,
  fetchRecentlyPlayed,
  fecthFeaturedPlaylists,
  fetchPodcastEpisodes,
  fetchMoreLikeArtists,
  fetchMixes,
  fetchPopularidad,
};

export default homeSlice.reducer;
