# ✅ RadioPV · Decisiones tomadas (David, 2026-08-28)

> Las cuatro decisiones que estaban marcadas `⏸️` en [`PROGRESS.md`](PROGRESS.md) quedan **cerradas**.
> El agente que implementa ya no necesita esperar por ellas. **No reabrir sin hablarlo.**

---

## D1 · Los ~1,62 GB en cuarentena → **mover, no borrar**

**Decisión**: los ficheros de las 16 pistas en `cuarentena` se **mueven** a `E:\Musica\_cuarentena\`,
conservando la estructura de carpetas. **No se borran.**

- Las filas se quedan en la BD con `status='cuarentena'` para que el recolector **no las vuelva a bajar**.
- Si en una semana no se echa nada de menos, David borra esa carpeta a mano de una vez.
- **El agente no borra ficheros de `E:\Musica` en ningún caso** (la regla 8 sigue en pie: mover sí,
  borrar no).

Contenido confirmado de esa cuarentena: ruido blanco de Deezer (1.025 MB + 106 MB + 26 MB + 5 MB),
`Disney - Zoo` (344 MB), una recopilación dance de 58 min, seis fragmentos de CSS/HTML tomados por
títulos, una intro de dibujos de 59 s y una intro de 50 s. Nada recuperable.

---

## D2 · T-21 `valence` / `danceability` → **opción B: quitarlos del documento**

**Decisión**: **no se calculan**. Se actualiza `docs/03_PERSONALIZATION.md` para que describa el
algoritmo que de verdad se ejecuta (`genre`, `era`, `artist`, `bpm`, `energy`, `rank`), y se marcan
`valence`/`danceability`/`acousticness`/`loudness` como **no implementadas**, no como "previstas para
ya".

**Motivo**: la aproximación de `valence` con librosa (heurística de modo mayor/menor + centroide
espectral) acierta regular y metería ruido en el perfil de gustos. Lo que sí cambia la experiencia es
`energy` bien normalizada (T-20) y `gain_db` (T-22). Si en el futuro se quiere más riqueza, será con
*embeddings* de audio, no con estas dos features.

**Consecuencia**: `03_PERSONALIZATION.md` deja de prometer lo que el código no hace. La columna
`valence` puede quedarse en el esquema, vacía y documentada como no usada.

---

## D3 · DP-01 dónde vive el audio → **A: en casa, por Tailscale. Sin exposición a internet**

**Decisión**: el backend corre en el PC de siempre y se llega a él por **Tailscale** (red privada).
**No se expone a internet**, no se sube nada a almacenamiento de objetos, no hace falta abrir puertos.

Consecuencias directas para el código:

- `GET /stream` se queda como **`FileResponse` local**. No hace falta el redirect firmado.
- **Sigue mereciendo la pena** escribir `servir_audio(track)` como función aparte (`13_DEPLOY_SPEC.md`
  DP-01), para que cambiar de idea más adelante sea una función y no una reescritura.
- No hay certificados que gestionar: dentro de Tailscale el tráfico ya va cifrado. (Tailscale ofrece
  HTTPS con nombre propio si se quiere; opcional.)
- **Se descarta Cloudflare Tunnel**: además de exponer públicamente, desaconseja el streaming de
  medios por el túnel gratuito.
- `ALLOWED_ORIGINS` se limita a la dirección Tailscale y a `localhost`.

**Esto responde también a "¿exponer a internet?": no.** Y con ello el asunto legal se simplifica: no
hay distribución a terceros, es acceso a tu propio disco desde tus propios dispositivos. Si algún día
entra gente de fuera del hogar, se revisa **esta decisión primero**.

---

## D4 · ¿Una base de datos o dos? → **dos, por ahora**

**Decisión**: se mantienen `data/radiov.db` (recolector) y `data/backend.db` (API), sincronizadas por
la migración no destructiva (T-05), que ya es idempotente y conserva las señales de usuario.

**Motivo**: el problema que hacía urgente unificarlas (la migración destructiva) **ya está resuelto**.
Unificar hoy es mover cosas sin ganar nada.

**Cuándo reabrirlo**: si el retraso de 30 minutos entre lo que baja el recolector y lo que ve la app
llega a molestar. Entonces el camino es que el recolector escriba directo en la BD del backend.

---

## D5 · Features de la UI sin equivalente en la API (descubrimiento de FE-05)

| Feature de la UI | Decisión | Por qué |
|---|---|---|
| `followArtists` / seguir artistas | **Añadir al backend** (`follows` + 3 endpoints) | "Tus artistas" es una sección real de la app y es barato |
| `fetchTopArtists` / `fetchTopTracks` | **Añadir** como `GET /library/top?type=artists\|tracks&period=` | Sale de `plays`, que ya se registra. Es el "On Repeat" |
| `fetchQueue` / cola en servidor | **Quitar de la UI** | La cola vive en el cliente (Redux). Decisión ya tomada en `08_REVIEW.md` §5.3 |
| `devices` / selector de dispositivos | **Quitar de la UI** | Es Spotify Connect: fuera del alcance |
| `episodes` / podcasts | **Quitar de la UI** | No hay podcasts en el catálogo |

---

## Recordatorio de la regla que sigue vigente

Estas decisiones cierran las que estaban pendientes. **La regla 10 no desaparece**: si aparece una
decisión nueva de producto, de dinero, de datos irreversibles o de exposición a terceros, el agente
para y pregunta.
