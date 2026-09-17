import { createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';

import type { RootState } from '../store';

export interface UiState {
  queueCollapsed: boolean;
  devicesCollapsed: boolean;
  detailsCollapsed: boolean;
  libraryCollapsed: boolean;
  loginTooltipOpen: boolean;
  loginButtonOpen: boolean;
  loginModalOpen: boolean;
  loginModalItem: string | null;
}

const initialState: UiState = {
  queueCollapsed: true,
  devicesCollapsed: true,
  detailsCollapsed: true,
  libraryCollapsed: true,
  loginTooltipOpen: false,
  loginButtonOpen: false,
  loginModalOpen: false,
  loginModalItem: null,
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    openLoginButton(state) {
      state.loginButtonOpen = true;
      state.loginModalItem = null;
      state.loginTooltipOpen = false;
    },
    closeLoginButton(state) {
      state.loginButtonOpen = false;
    },
    /**
     * Abre el modal de acceso.
     *
     * La imagen es OPCIONAL y solo decora: antes el modal solo se dibujaba si había imagen
     * (`if (!imgUrl) return null`), así que los botones de "Iniciar sesión" —que no vienen de
     * ninguna canción ni álbum— no tenían forma de abrirlo y había que pasarles algo. Ahora
     * manda `loginModalOpen`, y sin imagen se usa el logo de la app.
     */
    openLoginModal(state, action: PayloadAction<string | undefined>) {
      state.loginModalItem = action.payload || null;
      state.loginModalOpen = true;
      state.loginButtonOpen = false;
      state.loginTooltipOpen = false;
    },
    closeLoginModal(state) {
      state.loginModalOpen = false;
      state.loginModalItem = null;
    },
    openLoginTooltip(state) {
      state.loginTooltipOpen = true;
      state.loginModalItem = null;
      state.loginButtonOpen = false;
    },
    closeLoginTooltip(state) {
      state.loginTooltipOpen = false;
    },
    collapseDetails(state) {
      state.detailsCollapsed = true;
    },
    toggleDetails(state) {
      state.queueCollapsed = true;
      state.libraryCollapsed = true;
      state.devicesCollapsed = true;
      state.detailsCollapsed = !state.detailsCollapsed;
    },
    collapseLibrary(state) {
      state.libraryCollapsed = true;
    },
    openLibrary(state) {
      state.libraryCollapsed = false;
    },
    toggleLibrary(state) {
      state.libraryCollapsed = !state.libraryCollapsed;
    },
    collapseQueue(state) {
      state.queueCollapsed = true;
    },
    toggleQueue(state) {
      state.detailsCollapsed = true;
      state.libraryCollapsed = true;
      state.devicesCollapsed = true;
      state.queueCollapsed = !state.queueCollapsed;
    },
    collapseDevices(state) {
      state.devicesCollapsed = true;
    },
    toggleDevices(state) {
      state.detailsCollapsed = true;
      state.libraryCollapsed = true;
      state.queueCollapsed = true;
      state.devicesCollapsed = !state.devicesCollapsed;
    },
  },
});

export const isRightLayoutOpen = createSelector(
  [
    (state: RootState) => state.ui.queueCollapsed,
    (state: RootState) => state.ui.devicesCollapsed,
    (state: RootState) => state.ui.detailsCollapsed,
  ],
  (queueCollapsed, devicesCollapsed, detailsCollapsed) => {
    return !queueCollapsed || !devicesCollapsed || !detailsCollapsed;
  }
);

export const getLibraryCollapsed = createSelector(
  [(state: RootState) => state.ui.libraryCollapsed, (state: RootState) => state.auth.user],
  (libraryCollapsed, user) => {
    return !user ? false : libraryCollapsed;
  }
);

export const uiActions = {
  ...uiSlice.actions,
};

export default uiSlice.reducer;
