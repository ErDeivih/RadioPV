/** Único punto de verdad para el token de sesión.
 *  Se guarda EN CRUDO (el JWT ya lleva su propio `exp`); no se envuelve en {value, expiry}.
 *  Mezclar los dos formatos rompía el arranque: `axios.ts` hacía JSON.parse de un JWT al cargar
 *  el módulo → excepción → React no montaba → PÁGINA EN BLANCO. */
export const getToken = (): string | null => localStorage.getItem('access_token');
export const setToken = (t: string) => localStorage.setItem('access_token', t);
export const clearToken = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('stream_token');
};
