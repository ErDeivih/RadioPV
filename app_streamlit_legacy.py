from __future__ import annotations

import os
import pandas as pd
import streamlit as st

from radiov import db
from radiov import models as M
from radiov import activity as A
from radiov import blacklist as B
from radiov import playlist as PL
from radiov.agent import get_manager
from radiov.config import load_settings


@st.cache_data(ttl=30)
def _cached_stats() -> dict:
    return db.stats()


@st.cache_data(ttl=30)
def _cached_progress() -> dict:
    return db.catalog_progress()


@st.cache_data(ttl=300, max_entries=40)
def _cached_stats_detail() -> dict:
    return db.stats_detail()


@st.cache_data(ttl=600, max_entries=40)
def _audio_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


# ----------------------------------------------------------------------------
# Configuración de la página y arranque
# ----------------------------------------------------------------------------
st.set_page_config(page_title="RadioPV · Mi Spotify propio", page_icon="📻", layout="wide")
db.init_db()
mgr = get_manager()  # arranca el trabajador en segundo plano (una sola vez)


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _human_bpm(t: dict) -> str:
    if t.get("bpm") is None:
        return "—"
    if t.get("tempo_est") == M.TEMPO_ANALYZED:
        return f"{t['bpm']:.0f} (real)"
    return f"{t['bpm']:.0f} (est.)"


def tracks_df(tracks: list[dict]) -> pd.DataFrame:
    rows = []
    for t in tracks:
        rows.append({
            "id": t["id"],
            "Artista": t.get("artist") or "",
            "Feat": (t.get("feat") or "")[:36],
            "Título": t.get("title") or "",
            "Álbum": (t.get("album") or "")[:40],
            "Género": M.GENRE_LABELS.get(t.get("genre"), t.get("genre") or "Variado"),
            "Idioma": M.LANGUAGE_LABELS.get(t.get("language"), "Otro"),
            "Año": str(t.get("year") or ""),
            "Era": t.get("era") or "",
            "BPM": _human_bpm(t),
            "Energía": ("Alta" if (t.get("energy") or 0) >= 0.55 else "Media" if (t.get("energy") or 0) >= 0.3 else "Baja") if t.get("energy") is not None else "—",
            "Remix": "✅" if t.get("is_remix") else "—",
            "Etiquetas": ",".join((t.get("tags") or "").split(",")[:4]) if t.get("tags") else "",
            "Dur": f"{int(t.get('duration') or 0)//60}:{int(t.get('duration') or 0)%60:02d}",
            "Fuente": t.get("source") or "",
            "Ritmo de": ", ".join(k for k in A.activity_keys() if A.matches_activity(t, k)) or "—",
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Barra lateral
# ----------------------------------------------------------------------------
st.sidebar.title("📻 RadioPV")
st.sidebar.caption("Buscador y descargador de música popular desde YouTube")
stats = _cached_stats()
st.sidebar.metric("Canciones en biblioteca", stats["total"])
st.sidebar.caption(f"Descargadas: {stats['downloaded']} · Con BPM: {stats['analyzed']} · {_fmt_size(stats['size_bytes'])}")

page = st.sidebar.radio("Sección", [
    "🏠 Panel", "🎵 Biblioteca", "🎧 Escuchar y decidir", "🎤 Artistas", "📊 Estadísticas",
    "⬇️ Descargas y Agente", "🏊 Lista para auriculares", "🚫 Lista negra",
])

# ----------------------------------------------------------------------------
# PÁGINA: Panel
# ----------------------------------------------------------------------------
def page_dashboard():
    st.header("🏠 Panel de estado")
    snap = mgr.snapshot()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Agente automático", "🟢 ACTIVO" if snap["enabled"] else "⚪ PARADO")
    c2.metric("Trabajador", "🟢 en marcha" if snap["running"] else "⚪ inactivo")
    c3.metric("Cola de pedidos", snap["queue"])
    c4.metric("Descargas del agente", snap["done"])

    st.subheader("📈 Progreso del catálogo")
    pg = _cached_progress()
    total = max(pg["total"], 1)
    for label, val in [("🎚️ Con BPM", pg["bpm"]), ("⚡ Con energía", pg["energy"]),
                       ("🕵️ Metadatos revisados", pg["reviewed"]), ("🏷️ Con etiquetas", pg["tagged"])]:
        st.write(f"{label}: **{val}** de {pg['total']}")
        st.progress(val / total)
    st.caption("Si ves que faltan BPM o energía, pon el modo del trabajador en «🎚️ Analizar BPM» o «⚡ Calcular energía».")

    st.divider()
    st.subheader("🎲 Recomendaciones del día")
    st.caption("Una selección aleatoria de tu biblioteca, tipo «mix diario». Elige un mood si quieres y genera.")
    rm = st.selectbox("Mood", ["(todos)"] + list(M.MOODS), key="rec_mood")
    if st.button("🎲 Generar mix del día"):
        mood = None if rm == "(todos)" else rm
        picks = db.random_tracks(15, mood=mood)
        st.session_state["rec_picks"] = [p["id"] for p in picks]
        st.rerun()
    rec_tracks = []
    for _id in st.session_state.get("rec_picks", []):
        _t = db.get_track_by_id(_id)
        if _t:
            rec_tracks.append(_t)
    if rec_tracks:
        st.dataframe(tracks_df(rec_tracks), width="stretch", hide_index=True)
        st.caption("Para escucharlas, pasa a «🎧 Escuchar y decidir».")

    with st.container():
        st.subheader("🕹️ Control del agente")
        enabled = st.toggle("Agente automático (crecer la biblioteca solo)", value=snap["enabled"])
        if enabled != snap["enabled"]:
            mgr.set_agent(enabled)
            st.rerun()
        if snap["current"]:
            st.info(f"Ahora: **{snap['current']}**")
        st.write(f"Último: {snap['last'] or '—'}")
        mode_map = {
            "auto": "🌐 Todo automático (recomendado)",
            "descargas": "⬇️ Descargar música (agente)",
            "revision": "🕵️ Revisar metadatos",
            "bpm": "🎚️ Analizar BPM pendientes",
            "energia": "⚡ Calcular energía",
        }
        cur_mode = snap.get("mode", "auto")
        mode = st.selectbox("🎛️ ¿En qué quieres que trabaje ahora?", list(mode_map),
                            format_func=lambda k: mode_map[k], index=list(mode_map).index(cur_mode))
        if mode != cur_mode:
            mgr.set_mode(mode)
            st.rerun()
        st.caption("Parte de listas de éxitos (España/E.E.U.U. y por años) y expande por géneros e idiomas "
                   "(reggaetón, pop, rock, bachata, salsa, merengue, cumbia, corridos, flamenco, dance, rap, "
                   "italiano, francés, portugués…) sin listas cerradas de artistas.")
        b1, b2, b3 = st.columns(3)
        if b1.button("🕵️ Revisar metadatos"):
            mgr.review_now()
            st.success("Revisión en cola. Pasará canción a canción corrigiendo año, álbum, carátulas y artistas.")
        if b2.button("🎤 Actualizar perfiles de artistas"):
            mgr.artists_now()
            st.success("Enviado. Se rellena foto/fans/álbumes de los artistas.")
        if b3.button("🧹 Limpiar lo vetado"):
            mgr.purge_now()
            st.success("Enviado al trabajador")
        if mgr.reviewing:
            cur = mgr.progress.get("current_review")
            st.info(f"🕵️ **Revisando metadatos…** {('· ' + cur) if cur else ''}")
        elif mgr.review_report:
            st.success(f"✅ Última revisión terminada: **{mgr.review_report.get('n')}** canciones corregidas.")
        st.caption("El BPM se calcula automáticamente al descargar y el **revisor de metadatos** y el re-análisis "
                   "de BPM corren solos de vez en cuando. El botón «Revisar metadatos» lanza una pasada ahora mismo. "
                   "El revisor **corrige datos, no añade canciones**: para que crezca la lista debe estar activo el agente.")
        st.caption("El BPM se calcula automáticamente al descargar. El botón reintenta las que no se pudieron analizar. "
                   "«Limpiar lo vetado» borra las canciones marcadas en la lista negra, **pero la lista negra se conserva**: "
                   "el agente no las volverá a descargar.")

    st.divider()
    st.subheader("🎖️ Prioridades (canción, artista o álbum)")
    st.caption("Escribe una entrada por línea: el sistema decide si es un artista, un álbum o una canción, "
               "y descarga primero sus temas más conocidos (tiene prioridad sobre el agente).")
    prio_key = st.session_state.get("prio_key", 0)
    prio = st.text_area("Cada línea es una entrada", height=130, key=f"prio_box_{prio_key}",
                        placeholder="Shakira\nUn Verano Sin Ti\nWaka Waka\nAndrea Bocelli")
    if st.button("🚀 Enviar prioridades"):
        n = mgr.enqueue_priority(prio)
        st.session_state["prio_key"] = prio_key + 1
        st.success(f"{n} prioridades en cola (se descargan antes que el agente). ")
        st.rerun()

    st.divider()
    st.subheader("✍️ Pedir por texto (lenguaje natural)")
    st.caption("Escribe lo que falte con tus palabras (una frase): se entiende y se busca. "
               "Ej.: «más canciones de 2015», «más flamenco», «algo de Bad Bunny».")
    nat_key = st.session_state.get("nat_key", 0)
    nat = st.text_area("Petición", height=90, key=f"nat_box_{nat_key}",
                       placeholder="más canciones de 2015\nmás flamenco\nmás de Bad Bunny")
    if st.button("🔎 Enviar petición"):
        n = mgr.enqueue_natural(nat)
        st.session_state["nat_key"] = nat_key + 1
        st.success(f"{n} petición(es) encolada(s). ")
        st.rerun()

    st.divider()
    from radiov.config import load_settings as _ls
    _cfg = _ls()
    st.subheader("🗂️ Carpetas de la biblioteca")
    st.write(f"⬇️ Descargas **en bruto**: `{_cfg['download_dir']}`")
    st.write(f"📁 Catálogo **organizado/etiquetado**: `{_cfg['catalog_dir']}`")
    st.write(f"🎧 **Auriculares** (subselecciones): `{_cfg['playlist_dir']}`")
    st.caption("Cada canción se etiqueta con artista, álbum, año, género y BPM, y se organiza por artista dentro de catalogada.")
    if st.button("📂 Reorganizar biblioteca ahora"):
        mgr.reorganize_now()
        st.success("Enviado al trabajador. Moverá los temas a catalogada.")

    st.subheader("📊 Distribución por género")
    if stats["by_genre"]:
        df = pd.DataFrame([{"Género": M.GENRE_LABELS.get(k, k), "Canciones": v}
                           for k, v in sorted(stats["by_genre"].items(), key=lambda x: -x[1])])
        st.bar_chart(df.set_index("Género"))
    else:
        st.info("Aún no hay canciones. Ve a «Descargas y Agente» para empezar.")

    st.subheader("🌐 Idiomas")
    if stats["by_language"]:
        st.write({M.LANGUAGE_LABELS.get(k, k): v for k, v in stats["by_language"].items()})

    st.subheader("🧾 Actividad reciente")
    events = db.recent_events(40)
    if events:
        st.table(pd.DataFrame(
            [{"Fecha": e["ts"], "Nivel": e["level"], "Mensaje": e["message"]} for e in events]))


# ----------------------------------------------------------------------------
# PÁGINA: Biblioteca
# ----------------------------------------------------------------------------
def page_library():
    st.header("🎵 Biblioteca")
    st.caption("Marca canciones con el checkbox, selecciona por álbum/artista y borra con aviso. "
               "Vetar = no se volverá a descargar.")

    st.markdown("**🔍 Ir a un artista** (escribe y selecciona para ver solo ese artista)")
    artists_list = ["(todos)"] + sorted(db.distinct_values("artist"))
    goto = st.selectbox("Artista", artists_list, key="lib_goto", label_visibility="collapsed")

    fcol1, fcol2, fcol3 = st.columns([3, 2, 2])
    text = fcol1.text_input("Buscar (título, artista, álbum)", key="lib_search")
    genres = ["Todos"] + sorted(db.distinct_values("genre"))
    genre = fcol2.selectbox("Género", genres, key="lib_genre")
    langs = ["Todos"] + sorted(db.distinct_values("language"))
    lang = fcol3.selectbox("Idioma", langs, key="lib_lang")

    r2 = st.columns(5)
    years = ["Todos"] + [str(y) for y in db.distinct_years()]
    year = r2[0].selectbox("Año", years, key="lib_year")
    eras = ["Todas"] + db.distinct_eras()
    era = r2[1].selectbox("Era", eras, key="lib_era")
    moods = ["(ninguno)"] + list(M.MOODS)
    mood = r2[2].selectbox("Mood", moods, key="lib_mood")
    energy = r2[3].selectbox("Energía", ["Toda", "Alta", "Media", "Baja"], key="lib_energy")
    remix = r2[4].selectbox("Remix", ["Todos", "Solo remixes"], key="lib_remix")

    filters = dict(search=text or None, artist=(None if goto == "(todos)" else goto))
    if genre != "Todos":
        filters["genre"] = genre
    if year != "Todos":
        filters["year"] = int(year)
    if lang != "Todos":
        filters["language"] = lang
    if era != "Todas":
        filters["era"] = era
    if mood != "(ninguno)":
        filters["tags"] = [mood]
    if energy != "Toda":
        lo = {"Baja": (0, 0.3), "Media": (0.3, 0.55), "Alta": (0.55, 1.01)}[energy]
        filters["energy_min"], filters["energy_max"] = lo[0], lo[1]
    if remix == "Solo remixes":
        filters["is_remix"] = True
    tracks = db.get_tracks(**filters, limit=700)

    if not tracks:
        st.info("No hay canciones con ese filtro.")
        return

    # Tabla ligera con selección múltiple por checkbox (rápida)
    df = tracks_df(tracks)
    event = st.dataframe(df, width="stretch", height=780, hide_index=True, key="lib_sel",
                         on_select="rerun", selection_mode="multi-row")
    sel_rows = list(getattr(getattr(event, "selection", None), "rows", []))
    sel_ids = {tracks[i]["id"] for i in sel_rows if i < len(tracks)}

    st.caption(f"{len(tracks)} canciones mostradas · **{len(sel_ids)} seleccionadas**")
    if sel_ids:
        with st.expander("👁️ Ver seleccionadas", expanded=False):
            st.dataframe(tracks_df([t for t in tracks if t["id"] in sel_ids]), width="stretch", hide_index=True)
        black = st.checkbox("Añadir a la lista negra (no se volverán a descargar)", value=True)
        confirm = st.checkbox("Confirmar borrado (no se puede deshacer)", value=False)
        if st.button("🗑️ Borrar seleccionadas", type="primary"):
            if not confirm:
                st.error("Marca «Confirmar borrado» para ejecutar.")
            else:
                deleted = B.delete_tracks(list(sel_ids), veto=black)
                st.success(f"{deleted} canciones borradas.")
                st.rerun()

    with st.expander("🚫 Vetar un artista o una canción concreta"):
        opts = {f"#{t['id']} · {t['artist']} — {t['title']}": t["id"] for t in tracks}
        tt = st.selectbox("Canción", list(opts.keys()))
        tid = opts[tt]
        c = st.columns(3)
        if c[0].button("Vetar canción (sin borrar)"):
            B.blacklist_song_only(tid)
            st.rerun()
        if c[1].button("Borrar y vetar"):
            B.block_song(tid)
            st.rerun()
        if c[2].button("Vetar artista completo"):
            tr = db.get_track_by_id(tid)
            B.block_artist(tr["artist"])
            st.rerun()


# ----------------------------------------------------------------------------
# PÁGINA: Descargas y Agente
# ----------------------------------------------------------------------------
def page_downloads():
    st.header("⬇️ Descargas y Agente")
    snap = mgr.snapshot()

    st.subheader("🤖 Agente automático")
    enabled = st.toggle("Activar agente (busca y descarga música conocida solo)", value=snap["enabled"])
    if enabled != snap["enabled"]:
        mgr.set_agent(enabled)
        st.rerun()
    p1, p2 = st.columns(2)
    p1.metric("Estado", "ACTIVO" if snap["enabled"] else "PARADO")
    p2.metric("Descargadas por el agente", snap["done"])
    st.write(f"Semilla actual: **{snap['current'] or '—'}**")
    st.write(f"Último: {snap['last'] or '—'}")
    md = {"auto": "🌐 Todo automático", "descargas": "⬇️ Descargar", "revision": "🕵️ Revisar",
          "bpm": "🎚️ BPM", "energia": "⚡ Energía"}
    _mode = st.selectbox("🎛️ Trabajador centrado en:", list(md), format_func=lambda k: md[k],
                         index=list(md).index(snap.get("mode", "auto")), key="dl_mode")
    if _mode != snap.get("mode", "auto"):
        mgr.set_mode(_mode)
        st.rerun()
    st.caption(f"Recorre {snap['n_seeds']} fuentes (listas de éxitos y expansión continua).")

    st.divider()
    st.subheader("🎯 Peticiones bajo demanda")
    od_song_key = st.session_state.get("od_song_key", 0)
    q = st.text_input("Canción (acepta «Artista - Título» o solo el título)", key=f"od_song_{od_song_key}",
                      placeholder="Shakira - Waka Waka")
    if st.button("⬇️ Descargar canción"):
        if q.strip():
            mgr.enqueue_text(q.strip())
            st.session_state["od_song_key"] = od_song_key + 1
            st.success("Petición en cola. Se descargará en breve.")
            st.rerun()
        else:
            st.warning("Escribe una canción.")

    st.subheader("📃 Descargar una lista (playlist) de YouTube")
    od_playlist_key = st.session_state.get("od_playlist_key", 0)
    url = st.text_input("URL de la playlist de YouTube", key=f"od_playlist_{od_playlist_key}",
                        placeholder="https://www.youtube.com/playlist?list=...")
    if st.button("⬇️ Descargar playlist"):
        if url.strip():
            mgr.enqueue_playlist(url.strip())
            st.session_state["od_playlist_key"] = od_playlist_key + 1
            st.success("Playlist en cola.")
            st.rerun()
        else:
            st.warning("Pega una URL válida.")

    st.subheader("📦 Procesos útiles")
    if st.button("🧹 Limpiar lo vetado"):
        mgr.purge_now()
        st.success("Enviado.")
    pending = len(db.get_tracks_needing_bpm(limit=500))
    st.caption(f"BPM pendientes de analizar: {pending} (se re-intentan automáticamente en el mantenimiento).")


# ----------------------------------------------------------------------------
# PÁGINA: Lista para auriculares
# ----------------------------------------------------------------------------
def page_playlist():
    st.header("🏊 Lista para auriculares")
    st.caption("Genera una subselección aleatoria según el ritmo que prefieras y guarda los MP3 en la carpeta **auriculares** para copiarlos al almacenamiento interno de tus cascos.")

    act = A.activity_keys()
    labels = {k: A.activity_label(k) for k in act}

    def _fmt(k):
        lo, hi = A.activity_bpm_range(k)
        lo_s = int(lo) if lo is not None else "?"
        hi_s = int(hi) if hi is not None else "?"
        return f"{labels[k]}  ·  {lo_s}–{hi_s} BPM"

    act_key = st.selectbox("Actividad / ritmo", act, format_func=_fmt)
    lo, hi = A.activity_bpm_range(act_key)
    st.caption(f"Rango de BPM: {int(lo)}–{int(hi)}")
    st.info(A.activity_desc(act_key))

    with st.expander("ℹ️ Guía de ritmos por actividad (BPM y por qué)"):
        for k in act:
            lo, hi = A.activity_bpm_range(k)
            st.markdown(f"**{labels[k]}**: {int(lo)}–{int(hi)} BPM — {A.activity_desc(k)}")

    c1, c2, c3 = st.columns(3)
    count = c1.number_input("Nº de canciones", min_value=1, max_value=int(load_settings().get("max_playlist_size", 200)), value=30)
    copy = c2.checkbox("Copiar los ficheros a la carpeta", value=True)
    include = c3.checkbox("Incluir canciones sin BPM (por género)", value=True)

    # Filtros opcionales
    st.subheader("🎛️ Filtrar la selección (opcional)")
    artists_all = ["Todos"] + sorted(db.distinct_values("artist"))
    genres_all = ["Todos"] + sorted(db.distinct_values("genre"))
    years_all = ["Todos"] + [str(y) for y in db.distinct_years()]
    eras_all = ["Todas"] + db.distinct_eras()
    f1, f2, f3 = st.columns(3)
    sel_artist = f1.selectbox("Artista prioritario", artists_all)
    sel_genre = f2.selectbox("Género", genres_all)
    sel_year = f3.selectbox("Año", years_all)
    f4, f5, f6 = st.columns(3)
    sel_era = f4.selectbox("Era", eras_all)
    sel_mood = f5.selectbox("Mood", ["(ninguno)"] + list(M.MOODS))
    sel_remix = f6.selectbox("Remix", ["Todos", "Solo remixes"])
    only_artists = None if sel_artist == "Todos" else [sel_artist]
    only_genres = None if sel_genre == "Todos" else [sel_genre]
    only_years = None if sel_year == "Todos" else [int(sel_year)]
    only_eras = None if sel_era == "Todas" else [sel_era]
    only_moods = None if sel_mood == "(ninguno)" else [sel_mood]
    only_remix = None if sel_remix == "Todos" else [sel_remix]

    tags_extra = list((only_moods or []))
    if only_remix:
        tags_extra.append("remix")
    if only_eras:
        tags_extra += only_eras

    if st.button("🎲 Generar lista aleatoria"):
        try:
            res = PL.generate_playlist(
                act_key, int(count), copy_files=copy, include_unclassified=include,
                artists=only_artists, genres=only_genres, years=only_years,
                tags=(tags_extra or None))
        except PL.PlaylistError as e:
            st.error(str(e))
            return
        st.success(f"Lista generada con {res['count']} canciones.")
        if res.get("destination"):
            st.write(f"📁 Carpeta: `{res['destination']}`")
            st.write(f"🎧 Lista: `{res['m3u']}`")
            st.caption("Copia el contenido de esa carpeta al almacenamiento de tus auriculares.")
        st.dataframe(tracks_df(res["tracks"]), width="stretch", hide_index=True)


# ----------------------------------------------------------------------------
# PÁGINA: Lista negra
# ----------------------------------------------------------------------------
def page_blacklist():
    st.header("🚫 Lista negra")
    st.caption("Artistas y canciones vetadas. El agente ya no los descargará y se eliminan de la biblioteca.")
    bl = B.list_blacklist()
    if not bl:
        st.info("La lista negra está vacía.")
        return
    rows = []
    for b in bl:
        rows.append({
            "id": b["id"],
            "Tipo": "Artista" if b["kind"] == M.BLACKLIST_ARTIST else "Canción",
            "Valor": b["value"],
            "Motivo": b.get("reason") or "",
            "Fecha": b.get("created_at") or "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True, key="bl_table")
    opts = {f"#{b['id']} · {b['value']}": b["id"] for b in bl}
    sel = st.selectbox("Retirar de la lista negra", list(opts.keys()))
    if st.button("➖ Retirar y permitir de nuevo"):
        B.unblock(opts[sel])
        st.success("Retirado. Se podrá descargar de nuevo.")
        st.rerun()


# ----------------------------------------------------------------------------
# PÁGINA: Escuchar y decidir
# ----------------------------------------------------------------------------
def page_listen():
    st.header("🎧 Escuchar y decidir")
    st.caption("Elige una canción, escúchala y decide: **borrar solo esta versión** (conservando la canción) "
               "o **vetar la canción** (ya no se descargará).")

    search = st.text_input("Filtrar (artista/título)", key="lst_search")
    genres = ["Todos"] + sorted(db.distinct_values("genre"))
    genre = st.selectbox("Género", genres, key="lst_genre")
    filt = {}
    if search:
        filt["search"] = search
    if genre != "Todos":
        filt["genre"] = genre
    tracks = db.get_tracks(**filt, limit=600)
    if not tracks:
        st.info("No hay canciones con ese filtro.")
        return
    st.caption(f"{len(tracks)} canciones (usa los filtros para acotar). **Haz clic en una fila** para verla.")
    df = tracks_df(tracks)
    event = st.dataframe(df, width="stretch", height=600, hide_index=True, key="lst_table",
                         on_select="rerun", selection_mode="single-row")
    sel_rows = list(getattr(getattr(event, "selection", None), "rows", []))
    if not sel_rows:
        st.info("Selecciona una canción de la tabla para escuchar y decidir.")
        return
    t = tracks[sel_rows[0]] if sel_rows[0] < len(tracks) else None
    if not t:
        return
    tid = t["id"]

    c = st.columns([2, 2])
    c[0].markdown(f"**{t['artist']}** — {t['title']}")
    info = []
    if t.get("year"):
        info.append(str(t["year"]))
    if t.get("album"):
        info.append(t["album"])
    if t.get("genre"):
        info.append(M.GENRE_LABELS.get(t["genre"], t["genre"]))
    if t.get("bpm"):
        info.append(f"BPM {round(t['bpm'])}")
    if t.get("feat"):
        info.append(f"feat {t['feat']}")
    if t.get("tags"):
        info.append(", ".join((t["tags"] or "").split(",")[:4]))
    c[1].caption(" · ".join(info))

    ic = st.columns(2)
    cover = t.get("cover_path") or t.get("cover_url")
    if cover:
        try:
            ic[0].image(cover, width=220, caption="💿 Álbum")
        except Exception:  # noqa: BLE001
            pass
    aimg = t.get("artist_image_path") or t.get("artist_image_url")
    if aimg:
        try:
            ic[1].image(aimg, width=220, caption="🎤 Artista")
        except Exception:  # noqa: BLE001
            pass

    fp = t.get("file_path")
    if st.button("▶️ Reproducir", key=f"play_{tid}"):
        st.session_state["playing_id"] = tid
    if st.session_state.get("playing_id") == tid and fp and os.path.exists(fp):
        try:
            st.audio(_audio_bytes(fp), format="audio/mp3")
        except Exception as e:  # noqa: BLE001
            st.warning(f"No se pudo reproducir: {e}")
    else:
        st.caption("El audio solo se carga cuando pulsas «▶️ Reproducir», para no ralentizar la navegación.")

    b1, b2 = st.columns(2)
    if b1.button("🗑️ Borrar esta versión (conservar la canción)"):
        B.remove_track_no_veto(tid)
        st.success("Borrada esta versión. La canción NO se ha vetado (podría volver a descargarse).")
        st.rerun()
    if b2.button("🚫 No me gusta esta canción (vetar y borrar)", type="primary"):
        B.block_song(tid)
        st.success("Canción borrada y vetada (ya no se descargará).")
        st.rerun()


# ----------------------------------------------------------------------------
# PÁGINA: Artistas
# ----------------------------------------------------------------------------
def page_artists():
    st.header("🎤 Artistas")
    st.caption("Perfiles y discografía de tu biblioteca. Se van completando al revisar metadatos y en el mantenimiento.")
    arts = db.get_artists(limit=200)
    if not arts:
        st.info("Todavía no hay perfiles. Se crearán al revisar metadatos (botón «🕵️ Revisar metadatos»).")
        return
    cols = st.columns(4)
    for i, a in enumerate(arts):
        with cols[i % 4]:
            img = a.get("image_path") or a.get("image_url")
            if img:
                try:
                    st.image(img, width=150)
                except Exception:  # noqa: BLE001
                    pass
            st.markdown(f"**{a['name']}**")
            st.caption(f"{a.get('track_count') or 0} canciones · {a.get('nb_fan') or 0} fans")

    st.divider()
    st.subheader("💿 Discografía")
    names = [a["name"] for a in arts]
    sel = st.selectbox("Artista", names, key="art_disc")
    albums = db.get_artist_albums(sel)
    if albums:
        st.caption(f"{len(albums)} álbumes de {sel}")
        cols2 = st.columns(4)
        for i, ab in enumerate(albums[:24]):
            with cols2[i % 4]:
                cov = ab.get("cover_url")
                if cov:
                    try:
                        st.image(cov, width=140)
                    except Exception:  # noqa: BLE001
                        pass
                st.markdown(f"{ab.get('title') or ''}")
                st.caption(str(ab.get("year") or ""))
    else:
        st.caption("Aún no hay discografía para este artista. Se rellena en «🎤 Actualizar perfiles de artistas».")


# ----------------------------------------------------------------------------
# PÁGINA: Estadísticas
# ----------------------------------------------------------------------------
def page_stats():
    st.header("📊 Estadísticas del catálogo")
    all_tracks = db.get_tracks(limit=100000)
    if not all_tracks:
        st.info("Aún no hay canciones. Ve a «Descargas y Agente» para empezar.")
        return
    rows = []
    for t in all_tracks:
        rows.append({
            "id": t["id"], "artista": t.get("artist") or "", "titulo": t.get("title") or "",
            "album": t.get("album") or "",
            "genero": M.GENRE_LABELS.get(t.get("genre"), t.get("genre") or "Variado"),
            "idioma": M.LANGUAGE_LABELS.get(t.get("language"), t.get("language") or "Otro"),
            "anio": t.get("year"), "bpm": t.get("bpm"), "dur": t.get("duration"),
            "origen": t.get("source") or "—",
        })
    df = pd.DataFrame(rows)
    s = _cached_stats()

    # ------- Filtros -------
    st.subheader("🔎 Filtrar")
    genres = sorted(x for x in df["genero"].unique() if x)
    langs = sorted(x for x in df["idioma"].unique() if x)
    f1, f2 = st.columns(2)
    sel_g = f1.multiselect("Géneros", genres, default=genres)
    sel_l = f2.multiselect("Idiomas", langs, default=langs)
    years = [int(y) for y in df["anio"].dropna().unique()] if df["anio"].notna().any() else [1990, 2025]
    lo_year, hi_year = min(years), max(years)
    f3, f4 = st.columns(2)
    y0 = f3.number_input("Año desde", min_value=1900, max_value=2030, value=max(1900, lo_year))
    y1 = f4.number_input("Año hasta", min_value=1900, max_value=2030, value=min(2030, hi_year))

    d = df[(df["genero"].isin(sel_g)) & (df["idioma"].isin(sel_l))]
    d = d[(d["anio"].fillna(0).astype(int) >= int(y0)) & (d["anio"].fillna(0).astype(int) <= int(y1))]
    st.caption(f"Mostrando **{len(d)}** de {len(df)} canciones.")

    c = st.columns(5)
    c[0].metric("Total", len(d))
    c[1].metric("Con BPM", int(d["bpm"].notna().sum()))
    c[2].metric("BPM medio", round(float(d["bpm"].mean()), 1) if d["bpm"].notna().any() else 0)
    c[3].metric("Duración media", f"{int(d['dur'].mean())//60}:{int(d['dur'].mean())%60:02d}" if d["dur"].notna().any() else "—")
    c[4].metric("Espacio", _fmt_size(s["size_bytes"]))

    st.subheader("🎵 Por género")
    g = d["genero"].value_counts()
    st.bar_chart(g)
    st.dataframe(g.rename_axis("Género").reset_index(name="Canciones"), width="stretch", hide_index=True)

    st.subheader("🌐 Por idioma")
    st.dataframe(d["idioma"].value_counts().rename_axis("Idioma").reset_index(name="Canciones"),
                 width="stretch", hide_index=True)

    if d["anio"].notna().any():
        st.subheader("📅 Por año")
        st.bar_chart(d["anio"].dropna().astype(int).value_counts().sort_index())
        st.subheader("📆 Por década")
        dec = (d["anio"].dropna().astype(int) // 10 * 10).value_counts().sort_index()
        st.bar_chart(dec)

    st.subheader("🎚️ Distribución de BPM")
    bpm = d["bpm"].dropna()
    if len(bpm):
        bins = [0, 60, 80, 100, 120, 140, 160, 180, 300]
        labs = ["<60", "60-80", "80-100", "100-120", "120-140", "140-160", "160-180", "180+"]
        st.bar_chart(pd.cut(bpm, bins=bins, labels=labs).value_counts().sort_index())

    st.subheader("⭐ Top artistas")
    st.dataframe(d.groupby("artista").size().reset_index(name="Canciones")
                 .sort_values("Canciones", ascending=False).head(25)
                 .rename(columns={"artista": "Artista"}), width="stretch", hide_index=True)

    st.subheader("💿 Top álbumes")
    alb = d[d["album"] != ""].groupby("album").size().reset_index(name="Canciones") \
        .sort_values("Canciones", ascending=False).head(20).rename(columns={"album": "Álbum"})
    st.dataframe(alb, width="stretch", hide_index=True)

    st.subheader("📥 Origen")
    st.dataframe(d["origen"].value_counts().rename_axis("Origen").reset_index(name="Canciones")
                 if "origen" in d else pd.DataFrame(), width="stretch", hide_index=True)

    st.caption("ℹ️ Para pedir más de lo que veas que falta, usa la caja «✍️ Pedir por texto (lenguaje natural)» del Panel.")
    st.download_button("⬇️ Exportar selección (CSV)",
                       d.drop(columns=["id"]).to_csv(index=False).encode("utf-8"),
                       "radiov.csv", "text/csv")


PAGES = {
    "🏠 Panel": page_dashboard,
    "🎵 Biblioteca": page_library,
    "🎧 Escuchar y decidir": page_listen,
    "🎤 Artistas": page_artists,
    "📊 Estadísticas": page_stats,
    "⬇️ Descargas y Agente": page_downloads,
    "🏊 Lista para auriculares": page_playlist,
    "🚫 Lista negra": page_blacklist,
}

if __name__ == "__main__":
    try:
        PAGES[page]()
    except Exception as e:  # noqa: BLE001
        st.error(f"Error: {e}")
        if os.environ.get("RADIOPV_DEBUG"):
            st.exception(e)
