# 📱 RadioPV · Especificación de la app móvil (Flutter) — FASE F5

> Tareas **MB-01 … MB-08**. Detalle ejecutable de la fase F5 de
> [`09_IMPLEMENTATION_PLAN.md`](09_IMPLEMENTATION_PLAN.md).
> Requiere **F0 + F1** terminadas y, en la práctica, F3 hecha antes (los mismos endpoints ya rodados
> en la web salen gratis aquí).

---

## 0. Punto de partida

`vendor/Flutter-Musive-app` — Flutter + Dart. Estructura verificada:

```
lib/
  api/url.dart                ← baseUrl 'cryptic-forest-99443.herokuapp.com', basePath '/api/v1'
  repositories/               get_home_page · get_one_song · get_search_results
                              get_artists_data · get_genre_data
  models/                     song_model · user · user_model · catagory · loading_enum
  screens/                    home · search · library · liked_songs · playlist · artist_profile
                              genre_page · recently_played · add_to_playlist · current_playing
  utils/                      player/ · play_list · bottom_play_widget · like_button
                              horizontal_songs_list · recent_search · sliver_appbar · loading
  controllers/main_controller.dart
  methods/                    get_greeting · get_response · log · snackbar
```

**Lo valioso que ya trae y NO hay que reescribir**: el reproductor con **notificación del sistema**,
la cola, los "me gusta", la búsqueda reciente y la **caché/offline**. En una app de música propia, lo
de descargar para escuchar sin datos es de lo más valorado, y aquí viene hecho.

### MB-01 · Preparar

```powershell
Copy-Item -Recurse vendor\Flutter-Musive-app mobile
cd mobile
flutter --version          # si no está: instalar Flutter SDK estable
flutter pub get
flutter analyze            # anotar los errores previos: no son culpa nuestra
```

⚠️ El repo es antiguo: es probable que haya que subir `pubspec.yaml` a versiones actuales de Dart y de
los paquetes (`just_audio`, `audio_service`, `http`). **Hacer eso primero, en un commit aparte**, y
solo cuando `flutter run` arranque la app original, empezar a cambiar endpoints. No mezclar las dos
cosas: si algo se rompe, no se sabría por cuál de las dos.

---

## MB-02 · Configuración y cliente HTTP

`lib/api/url.dart` — sustituir por configuración por entorno:

```dart
class Api {
  // --dart-define=API_BASE=http://192.168.1.50:8000
  static const String base = String.fromEnvironment(
      'API_BASE', defaultValue: 'http://10.0.2.2:8000');   // 10.0.2.2 = el PC desde el emulador
  static const String basePath = '';
}
```

> **Nota importante**: desde el emulador de Android, `127.0.0.1` es el propio emulador, **no** tu PC.
> Hay que usar `10.0.2.2`. Desde un móvil real, la IP de tu PC en la red local (`192.168.x.x`) y el
> backend arrancado con `--host 0.0.0.0`.

`lib/api/client.dart` (nuevo) — un único punto para el JWT:

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'url.dart';

class ApiClient {
  static String? _token;

  static Future<void> cargarToken() async {
    _token = (await SharedPreferences.getInstance()).getString('access_token');
  }

  static Map<String, String> get _cab => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  static Future<dynamic> get(String ruta) async {
    final r = await http.get(Uri.parse('${Api.base}$ruta'), headers: _cab);
    if (r.statusCode == 401) throw SesionCaducada();
    if (r.statusCode >= 400) throw Exception('GET $ruta -> ${r.statusCode}');
    return jsonDecode(utf8.decode(r.bodyBytes));       // utf8: hay tildes y ñ por todas partes
  }

  static Future<dynamic> post(String ruta, [Map<String, dynamic>? cuerpo]) async {
    final r = await http.post(Uri.parse('${Api.base}$ruta'),
        headers: _cab, body: jsonEncode(cuerpo ?? {}));
    if (r.statusCode >= 400) throw Exception('POST $ruta -> ${r.statusCode}');
    return r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
  }

  /// El login usa formulario (OAuth2PasswordRequestForm), no JSON.
  static Future<Map<String, dynamic>> login(String email, String clave) async {
    final r = await http.post(Uri.parse('${Api.base}/auth/login'),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {'username': email, 'password': clave});
    if (r.statusCode != 200) throw Exception('Credenciales incorrectas');
    final d = jsonDecode(r.body);
    _token = d['access_token'];
    await (await SharedPreferences.getInstance()).setString('access_token', _token!);
    return d;
  }
}

class SesionCaducada implements Exception {}
```

---

## MB-03 · Token de streaming (igual que en la web)

Aunque `just_audio` **sí** puede enviar cabeceras, se usa el **mismo token en la URL** que la web: un
solo camino de autenticación para el streaming, un solo sitio donde puede fallar.

```dart
class Stream_ {
  static String? _t;
  static DateTime _exp = DateTime.fromMillisecondsSinceEpoch(0);

  static Future<String> token() async {
    if (_t != null && DateTime.now().isBefore(_exp.subtract(const Duration(minutes: 1)))) return _t!;
    final d = await ApiClient.post('/auth/stream-token');
    _t = d['token'];
    _exp = DateTime.now().add(Duration(seconds: d['expires_in']));
    return _t!;
  }

  static Future<String> url(int trackId) async =>
      '${Api.base}/stream/$trackId?t=${Uri.encodeComponent(await token())}';
}
```

---

## MB-04 · Modelo de canción

`lib/models/song_model.dart` — mapear a nuestro `TrackOut`:

```dart
class Song {
  final int id;
  final String title, artist;
  final String? album, cover, era, genre;
  final double? duration, bpm, energy, gainDb;
  final bool explicit;

  Song.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        title = j['title'] ?? '',
        artist = j['artist'] ?? '',
        album = j['album'],
        cover = j['cover'] == null ? null : '${Api.base}${j['cover']}',
        era = j['era'], genre = j['genre'],
        duration = (j['duration'] as num?)?.toDouble(),
        bpm = (j['bpm'] as num?)?.toDouble(),
        energy = (j['energy'] as num?)?.toDouble(),
        gainDb = (j['gain_db'] as num?)?.toDouble(),
        explicit = j['explicit'] ?? false;
}
```

> `cover` llega como ruta relativa (`/media/covers/x.jpg`): se le antepone la base. La foto del
> artista **no** viene en la canción (está vacía en las 1114 filas): se pide a `/artists/{name}`.

---

## MB-05 · Repositorios

| Fichero | Antes | Ahora |
|---|---|---|
| `get_home_page.dart` | backend Node | `GET /recommend/daily` · `/playlists/system` · `/tracks?sort=rank` |
| `get_search_results.dart` | `/search` | `GET /tracks?q=` |
| `get_one_song.dart` | `/song/{id}` | `GET /tracks/{id}` |
| `get_artists_data.dart` | `/artist/{id}` | `GET /artists/{name}` + `/artists/{name}/top` |
| `get_genre_data.dart` | `/genre/{x}` | `GET /tracks?genre=x` |
| *(nuevo)* `library_repo.dart` | — | `/library/liked` · `/library/{id}/like\|skip\|play` |
| *(nuevo)* `playlists_repo.dart` | — | `/playlists` y su CRUD |

`methods/get_response.dart` se sustituye por `ApiClient`. Todas las llamadas pasan por ahí.

---

## MB-06 · Reproductor

En `lib/utils/player/`:

1. La fuente pasa a ser `await Stream_.url(song.id)`.
2. **Ganancia por canción** (`gain_db`, T-22): `player.setVolume(min(1.0, pow(10, gainDb/20)))`.
   Sin esto, el salto de volumen entre canciones es el defecto más audible de la app.
3. **Conservar** la notificación del sistema (`audio_service`) rellenando título, artista y **carátula**.
4. Enviar las señales igual que la web: `POST /library/{id}/play` al empezar y, al terminar o saltar,
   con `seconds_listened`, `completed` y `context`.
5. **Reproducción continua**: al agotarse la cola, `GET /recommend/radio?seed_track=<última>`.
6. **Offline**: conservar la caché del repo. Al descargar una canción, guardar también el `gain_db` y
   la carátula, para que sin red se comporte igual.

---

## MB-07 · Android

`android/app/src/main/AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
<uses-permission android:name="android.permission.WAKE_LOCK"/>

<application
    android:usesCleartextTraffic="true"   <!-- SOLO en desarrollo (HTTP en red local) -->
    ...>
```

⚠️ **Quitar `usesCleartextTraffic` en la build de producción**: con HTTPS (F6) no hace falta, y
dejarlo puesto es una puerta abierta. Mejor aún: `network_security_config.xml` que permita texto plano
**solo** para la IP local.

Build:

```powershell
flutter build apk --release --dart-define=API_BASE=https://radiopv.tudominio.com
# el APK queda en build\app\outputs\flutter-apk\app-release.apk
```

---

## MB-08 · Pantallas

| Pantalla | Cambio |
|---|---|
| `home` | "Mix diario", "Trending", "Tus artistas" |
| `search_page` / `search_results` | `/tracks?q=` con *debounce*; estado vacío con **"pedir esta canción"** |
| `library` / `liked_songs` | `GET /library/liked` |
| `artist_profile` | `/artists/{name}` + `/top` + `/albums` + botón **"Radio"** |
| `playlist` / `add_to_playlist` | CRUD contra `/playlists` |
| `genre_page` | `/tracks?genre=` |
| `recently_played` | `/library/history` |
| `current_playing` | añadir 👍👎, "añadir a playlist" y **temporizador de apagado** |
| *(nueva)* `login` | email + contraseña + código de invitación |
| *(nueva)* `ajustes` | ocultar contenido explícito · calidad de descarga · cerrar sesión |

---

## Criterios de aceptación de F5

- [ ] Login contra nuestra API y sesión persistente entre arranques.
- [ ] Una canción **suena** y se puede **buscar dentro de ella** (seek) — es la prueba de que el
      `Range` del backend funciona también en móvil.
- [ ] La notificación del sistema muestra carátula, título y controles.
- [ ] Volumen uniforme entre canciones (ganancia aplicada).
- [ ] Descargar una canción y reproducirla **en modo avión**.
- [ ] 👍 en el móvil cambia las recomendaciones **en la web** (mismo backend, misma cuenta).
- [ ] APK de release instalable en un móvil real.
