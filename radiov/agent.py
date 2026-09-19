from __future__ import annotations

import datetime
import queue
import threading
import time
from typing import Optional

from . import db
from . import models as M
from . import pipeline
from . import deezer
from .config import load_settings

# Modo de refresco del agente (segundos entre pasadas completas sobre las semillas)
AGENT_REFRESH_IDLE_SECONDS = 120


class AgentManager:
    """Singleton que ejecuta en segundo plano el agente de descargas y la cola bajo demanda."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stop = False
        self._started = False
        self._thread: Optional[threading.Thread] = None
        self.ondemand: "queue.Queue[dict]" = queue.Queue()
        self.agent_enabled = bool(load_settings().get("agent_enabled_by_default", False))
        self.seed_cursor = 0
        # El mantenimiento (revisor de metadatos, ganancia, carátulas, republicar) corre cada
        # `maintenance_interval_minutes`. El contador NO empieza en «ahora»: si empieza en ahora,
        # después de cada reinicio hay que esperar el intervalo entero, y con el autodespliegue
        # recreando el contenedor cada pocos minutos el mantenimiento **no llegaba a ejecutarse
        # nunca**. Medido el 19/09: la última pasada era de las 10:01 y a las 10:40 seguía sin
        # repetirse, con 128 canciones a medias esperando a que las completara.
        # Se deja un minuto de margen para que arranque lo demás (migraciones, planificador).
        intervalo_min = int(load_settings().get("maintenance_interval_minutes", 15))
        self._last_maintenance = time.time() - max(0, intervalo_min - 1) * 60
        self.mode = "auto"   # auto | descargas | revision | bpm | energia
        self.reviewing = False
        self.review_report = {}
        self.progress = {
            "running": False, "enabled": self.agent_enabled,
            "current": "", "last": "", "seen": 0, "done": 0, "stop": False,
            "queue": 0, "since": datetime.datetime.now().isoformat(timespec="seconds"),
        }

    # ---------- ciclo de vida ----------
    def start(self) -> None:
        with self._lock:
            if self._started and self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._started = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="radiov-worker")
        self._thread.start()
        db.log_event("Agente iniciado", "info")

    def stop(self) -> None:
        with self._lock:
            self._stop = True
        if self._thread:
            self._thread.join(timeout=5)

    # ---------- cola bajo demanda ----------
    def enqueue_text(self, text: str) -> None:
        self.ondemand.put({"type": "text", "value": text})
        db.log_event(f"🎯 Encolada petición: {text}", "info")

    def enqueue_playlist(self, url: str) -> None:
        self.ondemand.put({"type": "playlist", "value": url})
        db.log_event(f"🎯 Encolada playlist: {url}", "info")

    def enqueue_priority(self, lines: str) -> int:
        """Interpreta cada línea como artista/álbum/canción y le da prioridad de descarga."""
        n = 0
        for raw in (lines or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            item = pipeline.interpret_priority_line(line)
            if not item:
                continue
            self.ondemand.put({"type": "priority", "value": item})
            n += 1
        if n:
            db.log_event(f"🎖️ {n} prioridades encoladas", "info")
        return n

    def enqueue_natural(self, lines: str) -> int:
        """Interpreta frases en lenguaje natural (año, género, artista…) y las encola."""
        n = 0
        for raw in (lines or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            for item in pipeline.interpret_natural(line):
                self.ondemand.put({"type": "priority", "value": item})
                n += 1
        if n:
            db.log_event(f"🗣️ {n} peticiones naturales encoladas", "info")
        return n

    def catalog_now(self) -> None:
        self.ondemand.put({"type": "catalog", "value": ""})
        db.log_event("Analizando BPM pendiente", "info")

    def purge_now(self) -> None:
        self.ondemand.put({"type": "purge", "value": ""})
        db.log_event("Purgando lista negra", "info")

    def reorganize_now(self) -> None:
        self.ondemand.put({"type": "reorg", "value": ""})
        db.log_event("Reorganizando biblioteca en catalogada", "info")

    def review_now(self) -> None:
        self.ondemand.put({"type": "review", "value": ""})
        db.log_event("🕵️ Revisando metadatos de canciones descargadas", "info")

    def artists_now(self) -> None:
        self.ondemand.put({"type": "artists", "value": ""})
        db.log_event("🎤 Actualizando perfiles de artistas", "info")

    # ---------- agente automático ----------
    def set_agent(self, enabled: bool) -> None:
        if enabled:
            self.start()  # asegura que el trabajador está vivo
        with self._lock:
            self.agent_enabled = enabled
            self.progress["enabled"] = enabled
        db.log_event(f"Agente automático {'activado' if enabled else 'detenido'}", "info")

    def set_mode(self, mode: str) -> None:
        """Elige en qué se centra el trabajador: auto, descargas, revision, bpm o energia."""
        if mode not in ("auto", "descargas", "revision", "bpm", "energia"):
            return
        with self._lock:
            self.mode = mode
            self.progress["mode"] = mode
        db.log_event(f"🎛️ Modo de trabajo: {mode}", "info")

    # ---------- bucle del trabajador ----------
    def _loop(self) -> None:
        self.progress["running"] = True
        while True:
            try:
                with self._lock:
                    if self._stop:
                        break
                # 1) prioridad: peticiones bajo demanda
                job = self._pop_job()
                if job is not None:
                    self._process(job)
                    continue
                # mantenimiento periódico (metadatos + BPM) cuando no hay nada urgente
                self._maybe_maintenance()
                with self._lock:
                    mode = self.mode
                # 2) según el modo de trabajo elegido
                if mode == "revision":
                    self._run_review_pass()
                elif mode == "bpm":
                    self._run_bpm_pass()
                elif mode == "energia":
                    self._run_energy_pass()
                elif self.agent_enabled:
                    seed = self._next_seed()
                    if seed is not None:
                        self._run_seed(seed)
                    else:
                        time.sleep(min(AGENT_REFRESH_IDLE_SECONDS, 5))
                else:
                    time.sleep(0.4)
            except Exception as e:  # noqa: BLE001
                db.log_event(f"Error en el trabajador: {e}", "error")
                self.progress["last"] = f"error: {e}"
                time.sleep(1.0)
        self.progress["running"] = False

    def _pop_job(self) -> Optional[dict]:
        try:
            job = self.ondemand.get_nowait()
            return job
        except queue.Empty:
            return None

    def _run_review_pass(self) -> None:
        from . import catalog as C
        with self._lock:
            self.reviewing = True
            self.progress["current_review"] = ""
        try:
            n = C.review_all(limit=300, progress=self.progress)
        finally:
            with self._lock:
                self.reviewing = False
                self.review_report = {"n": n}
                self.progress.pop("current_review", None)
        with self._lock:
            self.progress["last"] = f"revisor: {n} con cambios"

    def _run_bpm_pass(self) -> None:
        from . import catalog as C
        n = C.catalog_pending()
        with self._lock:
            self.progress["last"] = f"BPM analizados: {n}"

    def _run_energy_pass(self) -> None:
        from . import catalog as C
        n = C.analyze_energy_missing(limit=40)
        with self._lock:
            self.progress["last"] = f"energías calculadas: {n}"

    def _maybe_maintenance(self) -> None:
        """El revisor de metadatos y el re-análisis de BPM corren solos cada X minutos."""
        interval = int(load_settings().get("maintenance_interval_minutes", 15))
        if time.time() - self._last_maintenance < interval * 60:
            return
        self._last_maintenance = time.time()
        db.log_event("🛠️ Mantenimiento automático (revisor de metadatos + BPM)", "info")
        try:
            from . import catalog as C
            with self._lock:
                self.reviewing = True
                self.progress["current_review"] = ""
            try:
                r = C.review_all(limit=120, progress=self.progress)
            finally:
                with self._lock:
                    self.reviewing = False
                    self.review_report = {"n": r}
                    self.progress.pop("current_review", None)
            b = C.catalog_pending()
            e = C.analyze_energy_missing(limit=80)
            g = C.analizar_gain_missing(limit=80)
            art = C.refresh_artist_profiles(limit=20)
            med = C.enrich_media(limit=100)
            img = C.fetch_media(limit=100)
            rep = C.republicar_completas(limit=600)
            # Las canciones cuyo fichero desapareció se marcaban 'perdida' y **nadie las volvía a
            # descargar**: desaparecían de la aplicación para siempre. La función existía
            # (`recuperar_perdidas`) y su propia documentación decía que se llamaba desde aquí…
            # pero no la llamaba nadie. De poco en poco (5 por pasada) porque cada una es una
            # descarga de YouTube.
            perd = C.recuperar_perdidas(limit=5)
            with self._lock:
                self.progress["last"] = (f"mantenimiento: {r} metadatos, {b} BPM, {e} energías, "
                                         f"{g} gain_db, {art} artistas, {med} metadatos, {img} imágenes, "
                                         f"{rep} republicadas, {perd} recuperadas")
        except Exception as e:  # noqa: BLE001
            db.log_event(f"Fallo en mantenimiento: {e}", "error")

    def _process(self, job: dict) -> None:
        t = job.get("type")
        with self._lock:
            self.progress["current"] = "bajo demanda"
        try:
            if t == "text":
                tid = pipeline.process_text(job["value"], source=M.SOURCE_ONDEMAND)
                self.progress["last"] = f"pedido: {job['value']} → {'✔' if tid else '✖'}"
            elif t == "playlist":
                n = pipeline.process_playlist(job["value"], source=M.SOURCE_ONDEMAND)
                self.progress["last"] = f"playlist: +{n}"
            elif t == "catalog":
                n = pipeline_catalog_pending()
                self.progress["last"] = f"BPM analizados: {n}"
            elif t == "purge":
                from . import blacklist as B
                n = B.purge()
                self.progress["last"] = f"purgadas: {n}"
            elif t == "reorg":
                from . import catalog as C
                n = C.reorganize_library()
                self.progress["last"] = f"reorganizadas en catalogada: {n}"
            elif t == "review":
                from . import catalog as C
                with self._lock:
                    self.reviewing = True
                    self.progress["current_review"] = ""
                try:
                    n = C.review_all(limit=80, progress=self.progress)
                finally:
                    with self._lock:
                        self.reviewing = False
                        self.review_report = {"n": n}
                        self.progress.pop("current_review", None)
                self.progress["last"] = f"metadatos revisados: {n} con cambios"
            elif t == "artists":
                from . import catalog as C
                n = C.refresh_artist_profiles(limit=60)
                self.progress["last"] = f"perfiles de artista: {n} actualizados"
            elif t == "priority":
                item = job.get("value") or {}
                n = pipeline.process_priority_item(item)
                self.progress["last"] = f"prioridad «{item.get('value')}»: +{n}"
        except Exception as e:  # noqa: BLE001
            db.log_event(f"Error procesando {t}: {e}", "error")
            self.progress["last"] = f"error en {t}: {e}"

    def _next_seed(self) -> Optional[dict]:
        seeds = load_settings().get("agent_seeds", [])
        if not seeds:
            return None
        with self._lock:
            idx = self.seed_cursor
        if idx >= len(seeds):
            # reinicia y sigue creciendo tras una pausa
            with self._lock:
                self.seed_cursor = 0
            time.sleep(min(AGENT_REFRESH_IDLE_SECONDS, 8))
            idx = 0
        with self._lock:
            self.seed_cursor = idx + 1
        return seeds[idx]

    def _run_seed(self, seed: dict) -> None:
        label = seed.get("query") or seed.get("genre") or "artistas"
        with self._lock:
            self.progress["current"] = f"semilla: {label}"
        client = deezer.DeezerClient()
        max_dl = int(load_settings().get("agent_downloads_per_seed_per_pass", 6))
        try:
            added = pipeline.process_seed(seed, client=client, progress=self.progress,
                                          max_downloads=max_dl)
        except Exception as e:  # noqa: BLE001
            db.log_event(f"Fallo en semilla {label}: {e}", "error")
            added = 0
        with self._lock:
            self.progress["done"] += added
            self.progress["last"] = f"«{label}»: +{added}"
        time.sleep(load_settings().get("agent_sleep_seconds", 1.0))

    # ---------- estado ----------
    def snapshot(self) -> dict:
        with self._lock:
            p = dict(self.progress)
            p["queue"] = self.ondemand.qsize()
            p["enabled"] = self.agent_enabled
            p["mode"] = self.mode
            p["running"] = bool(self._started and not self._stop) and p["running"]
            p["seed_cursor"] = self.seed_cursor
            p["n_seeds"] = len(load_settings().get("agent_seeds", []))
        return p

    def sigue_vivo(self) -> bool:
        """¿El hilo de trabajo sigue en pie?

        Lo necesita `run_collector.py` para poder reiniciarse. Un hilo que muere por una
        excepción no tumba el proceso: el contenedor sigue «arriba», el interruptor sigue en
        «activado» y el recolector **no descarga nada**, sin avisar a nadie. Es exactamente lo que
        pasó durante días: por dentro muerto y por fuera con cara de estar funcionando.
        """
        return bool(self._thread and self._thread.is_alive())


def pipeline_catalog_pending() -> int:
    from . import catalog as C
    return C.catalog_pending()


_manager: Optional[AgentManager] = None
_mlock = threading.Lock()


def get_manager() -> AgentManager:
    global _manager
    with _mlock:
        if _manager is None:
            _manager = AgentManager()
            _manager.start()
        return _manager
