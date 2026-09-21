export interface User {
  display_name?: string;
  external_urls?: {
    spotify: string;
  };
  href?: string;
  id?: string;
  // Lista de imágenes, NO una tupla de exactamente dos.
  //
  // Estaba declarada como `[{…}, {…}]` (dos elementos obligatorios), copiada de la forma que tiene
  // la respuesta de Spotify. Nuestra API no devuelve ninguna imagen de usuario, así que el adaptador
  // rellenaba las dos con `url: ''`: la foto del perfil salía como un `<img src="">` —un hueco— y
  // las pantallas que preguntan `user.images[0]?.url` para decidir si usar su imagen por defecto
  // creían que sí había foto. Ahora puede ir vacía y cada pantalla usa su relleno.
  images?: {
    url: string;
    height: number;
    width: number;
  }[];
  type?: string;
  uri?: string;
  followers?: {
    href: null;
    total: number;
  };
  country?: string;
  product?: string;
  explicit_content?: {
    filter_enabled: boolean;
    filter_locked: boolean;
  };
  email?: string;
  /**
   * ¿Es administrador? La API lo manda en `/auth/me`, pero el adaptador (`toUser`) **no lo
   * copiaba**, así que la interfaz creía que nadie era administrador: el panel de administración
   * contestaba 403 «Esta sección es solo para administradores» **aunque la API diera todos los
   * datos**. O sea: el panel existía, funcionaba por dentro, y era imposible abrirlo.
   */
  is_admin?: boolean;
}
