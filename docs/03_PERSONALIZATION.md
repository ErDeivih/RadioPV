# 🧠 RadioPV · Algoritmos de personalización

> Cómo convertir señales → perfil → recomendaciones / mixes. Implementado parcialmente en
> `backend/app/routers/recommend.py` y `radiov/db.py`; aquí se fija el algoritmo definitivo.

## 1. Señales (inputs)
- **Explícitas**: `reactions.liked` (👍), `reactions.skipped` (👎).
- **Implícitas**: `plays` (fuente, `completed`, `seconds_listened`), repeticiones, skip al 30 %.

**Ponderación recomendada** (por señal):
| Señal | peso |
|---|---|
| like 👍 | +3 |
| play completo (>=30 s) | +1 |
| play 50 % | -1 |
| skip al 30 % | -2 |
| skip inmediato | -3 |

**Recencia**: peso exponencial `w = exp(-dias/90)`. Los gustos "recientes" importan más.

## 2. Vector de canción (features)
`[bpm, energy, era(one-hot), genre(one-hot)]`  — **solo las features que existen de verdad**.

> ⚠️ **NO implementado**: `valence`, `danceability`, `acousticness`, `loudness`, `tags(one-hot)` y `language`
> están **fuera** del vector porque no se calculan (ver `DECISIONES.md` D2). `valence` es NULL en el 100 % de
> las filas; librosa las aproxima mal y la app se beneficia más de `energy` bien normalizada y `gain_db`.
> Si algún día se amplían, será con embeddings de audio, no con estas dos. El vector real está en
> `backend/app/personalization.py::vector()` (bpm, energy + one-hot de género y era).

## 3. Perfil de gustos (`taste_profile`)
`user_taste` = **media ponderada** de los vectores de los tracks señalizados (con pesos de señal×recencia).
Deriva:
- `preferred_genres` (top 6), `preferred_artists` (top 12), `preferred_eras` (top 6),
- `bpm_mean`, `energy_mean`.  <!-- NOTA: valence_mean/danceability_mean ya no existen (D2) -->

## 4. Recomendación (content-based)
```
score(candidato) =
    coseno(user_taste, vector_cancion)
  + sesgo_artista (si artista ∈ preferidos)   +1.5
  + sesgo_género  (si género ∈ preferidos)    +2.5
  + sesgo_era     (si era ∈ preferidos)       +1.5
  + cercanía_bpm  (1 - |bpm - bpm_mean|/100) * 1
  + cercanía_energía (1 - |energy - energy_mean|/0.6) * 1
  + popularidad (prior, para cold start)
```
- **Excluir**: ya marcadas (👍/👎) y ya escuchadas (en los últimos días).
- **Diversidad (MMR)**: penalizar repetir el mismo artista/género en la lista para que no sea monótona.

## 5. Colaborativa (multi-usuario)
- Matriz implícita `usuarios × canciones` (plays/likes) → **Matrix Factorization (ALS)** o **item-item cosine**.
- Con pocos usuarios, **item-item cosine** sufice: `sim(a,b)` por co-ocurrencia de señales.

## 6. Similitud / radios
`sim(a,b) = coseno(vector_a, vector_b)`. Precomputar `similar` (top-K vecinos por canción) para no hacer O(N²).
`radio(seed)` = vecinos del seed ordenados.

## 7. Mixes
- **Daily mix**: perfil (content) + aleatorio controlado + diversidad + "no repetir en 7 días".
- **Discover Weekly**: una variante con más énfasis en géneros/artistas **poco escuchados** pero afines.
- **On Repeat**: las más escuchadas últimamente.
- **Time Capsule**: por época/mood según la edad del usuario.
- **Wrapped**: agregados semanales (top artistas/géneros, minutos, "nuevos descubrimientos").

## 8. Cold start
Sin señales → **popularidad + novedad + mood explícito**. A medida que el perfil madura, se mezcla con
content-based (pondera gradualmente).

## 9. Actualización
- `taste_profile` se recalcula **en cada refresco** (diario) o tras N nuevas señales.
- En `recommend()` no recalcular a demanda si el perfil es reciente (usar tabla precomputada).

---

## Referencia de funciones (backend)
- `_profile(user, db) -> dict` (géneros/artistas/eras/bpm_mean/energy_mean)
- `_score(track, prof) -> float`
- `_candidates(db, user, mood)` (excluye vistas/saltos)
- `recommend(n, mood)` · `daily(n)` · `radio(seed_track, n)`
- (propuesto) `compute_all_similar(limit)` · `rebuild_mixes_for(user)` · `weekly_wrapped(user)`
