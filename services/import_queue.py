"""
Import Queue Service - Sequenzielle Dateiverarbeitung für IMPORT_MEDIDOK

Dieser Service stellt sicher, dass Dateien nacheinander dem externen Dienst
präsentiert werden. Erst wenn eine Datei vom Dienst gelöscht wurde, wird die
nächste Datei in das Import-Verzeichnis verschoben.
"""
import os
import time
import threading
import queue
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from services.logger import log
from services.file_utils import _os_rename_original


@dataclass
class ImportTask:
    """Einzelne Import-Aufgabe in der Warteschlange."""
    source_path: str
    filename: str
    session_id: str
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class ImportQueueService:
    """
    Verwaltet die sequenzielle Verarbeitung von Dateien für IMPORT_MEDIDOK.

    Funktionsweise:
    1. Dateien werden in eine Queue eingereiht
    2. Die erste Datei wird sofort in IMPORT_MEDIDOK verschoben
    3. Ein FileWatcher überwacht das Verzeichnis
    4. Wenn die Datei gelöscht wurde, wird die nächste verschoben
    """

    def __init__(self, import_dir: str, check_interval: float = 2.0):
        """
        Args:
            import_dir: Pfad zum IMPORT_MEDIDOK Verzeichnis
            check_interval: Intervall in Sekunden für FileWatcher-Checks
        """
        self.import_dir = Path(import_dir)
        self.check_interval = check_interval

        # Queue für wartende Dateien
        self.task_queue: queue.Queue[ImportTask] = queue.Queue()

        # Aktuell verarbeitete Datei
        self.current_task: Optional[ImportTask] = None
        self.current_file_path: Optional[Path] = None

        # Threading
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Statistiken
        self.stats = {
            'total_queued': 0,
            'total_processed': 0,
            'total_failed': 0,
            'current_queue_size': 0
        }

        log("🔄 ImportQueueService initialisiert")

    def start(self):
        """Startet den Worker-Thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            log("⚠️ ImportQueueService läuft bereits")
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        log("✅ ImportQueueService Worker gestartet")

    def stop(self):
        """Stoppt den Worker-Thread."""
        log("🛑 Stoppe ImportQueueService...")
        self._stop_event.set()

        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)

        log("✅ ImportQueueService gestoppt")

    def enqueue_file(self, source_path: str, filename: str, session_id: str) -> bool:
        """
        Fügt eine Datei zur Import-Queue hinzu.

        Args:
            source_path: Vollständiger Pfad zur Quelldatei (in OUTPUT_ROOT)
            filename: Zielname der Datei
            session_id: Session-ID für Tracking

        Returns:
            True wenn erfolgreich eingereiht
        """
        if not os.path.exists(source_path):
            log(f"❌ Quelldatei nicht gefunden: {source_path}", level="error")
            return False

        task = ImportTask(
            source_path=source_path,
            filename=filename,
            session_id=session_id
        )

        self.task_queue.put(task)

        with self._lock:
            self.stats['total_queued'] += 1
            self.stats['current_queue_size'] = self.task_queue.qsize()

        log(f"📥 Datei in Import-Queue eingereiht: {filename} (Queue-Größe: {self.task_queue.qsize()})")
        return True

    def _worker_loop(self):
        """Haupt-Worker-Loop: Verarbeitet Dateien sequenziell."""
        log("🔄 Worker-Loop gestartet")

        while not self._stop_event.is_set():
            try:
                # Hole nächste Aufgabe (non-blocking mit Timeout)
                try:
                    task = self.task_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                with self._lock:
                    self.stats['current_queue_size'] = self.task_queue.qsize()

                # Verarbeite Aufgabe
                self._process_task(task)

                # Markiere Aufgabe als erledigt
                self.task_queue.task_done()

            except Exception as e:
                log(f"❌ Fehler im Worker-Loop: {e}", level="error")
                import traceback
                log(traceback.format_exc(), level="error")
                time.sleep(1.0)

        log("🛑 Worker-Loop beendet")

    def _process_task(self, task: ImportTask):
        """
        Verarbeitet eine einzelne Import-Aufgabe.

        1. Verschiebt Datei nach IMPORT_MEDIDOK (oder überspringt wenn bereits dort)
        2. Wartet auf Löschung durch externen Dienst
        3. Signalisiert Erfolg/Fehler
        """
        log(f"📄 Verarbeite: {task.filename} (Session: {task.session_id})")

        # Zielpad bestimmen
        destination = self.import_dir / task.filename

        # Stelle sicher, dass Import-Verzeichnis existiert
        self.import_dir.mkdir(parents=True, exist_ok=True)

        # Prüfe ob Quelle und Ziel identisch sind
        source_resolved = Path(task.source_path).resolve()
        dest_resolved = destination.resolve()

        # Datei verschieben (nur wenn nicht bereits am Zielort)
        try:
            if source_resolved == dest_resolved:
                # Datei ist bereits am richtigen Ort
                log(f"ℹ️ Datei ist bereits in IMPORT: {task.filename}")

                with self._lock:
                    self.current_task = task
                    self.current_file_path = destination
            else:
                # Verwende gespeicherte Originalfunktion (vor OS-Patching in app.py)
                _os_rename_original(task.source_path, str(destination))
                log(f"✅ Datei verschoben nach IMPORT: {task.filename}")

                with self._lock:
                    self.current_task = task
                    self.current_file_path = destination

        except Exception as e:
            log(f"❌ Fehler beim Verschieben von {task.filename}: {e}", level="error")
            with self._lock:
                self.stats['total_failed'] += 1
            return

        # Warte auf Löschung durch externen Dienst
        self._wait_for_deletion(destination, task)

    def _wait_for_deletion(self, file_path: Path, task: ImportTask, max_wait_seconds: int = 300):
        """
        Wartet darauf, dass die Datei vom externen Dienst gelöscht wird.

        Args:
            file_path: Pfad zur überwachten Datei
            task: Zugehörige Import-Aufgabe
            max_wait_seconds: Maximale Wartezeit in Sekunden (Standard: 5 Minuten)
        """
        log(f"⏳ Warte auf Löschung durch externen Dienst: {task.filename}")

        start_time = time.time()
        last_log_time = start_time

        while not self._stop_event.is_set():
            # Prüfe ob Datei noch existiert
            if not file_path.exists():
                elapsed = time.time() - start_time
                log(f"✅ Datei wurde vom Dienst verarbeitet und gelöscht: {task.filename} (nach {elapsed:.1f}s)")

                with self._lock:
                    self.current_task = None
                    self.current_file_path = None
                    self.stats['total_processed'] += 1

                return

            # Timeout-Check
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                log(f"⚠️ Timeout beim Warten auf Löschung: {task.filename} (nach {max_wait_seconds}s)", level="warning")
                log(f"   Die Datei existiert noch im Import-Verzeichnis. Fahre trotzdem fort.", level="warning")

                with self._lock:
                    self.current_task = None
                    self.current_file_path = None
                    self.stats['total_processed'] += 1
                    self.stats['total_failed'] += 1

                return

            # Logging alle 30 Sekunden
            if elapsed - last_log_time >= 30:
                log(f"⏳ Warte weiter auf Löschung: {task.filename} ({elapsed:.0f}s vergangen)")
                last_log_time = elapsed

            # Kurze Pause vor nächstem Check
            time.sleep(self.check_interval)

    def get_stats(self) -> Dict:
        """Gibt aktuelle Statistiken zurück."""
        with self._lock:
            stats = self.stats.copy()
            stats['current_file'] = self.current_task.filename if self.current_task else None
            stats['is_running'] = self._worker_thread and self._worker_thread.is_alive()

            # Stelle sicher, dass Queue-Größe aktuell ist
            stats['current_queue_size'] = self.task_queue.qsize()

            return stats

    def is_busy(self) -> bool:
        """Prüft ob aktuell eine Datei verarbeitet wird."""
        with self._lock:
            return self.current_task is not None

    def queue_size(self) -> int:
        """Gibt die aktuelle Queue-Größe zurück."""
        return self.task_queue.qsize()


# Globale Instanz
_import_queue_service: Optional[ImportQueueService] = None


def get_import_queue_service(import_dir: str) -> ImportQueueService:
    """
    Gibt die globale ImportQueueService-Instanz zurück.
    Erstellt sie beim ersten Aufruf.
    """
    global _import_queue_service

    if _import_queue_service is None:
        _import_queue_service = ImportQueueService(import_dir)
        _import_queue_service.start()

    return _import_queue_service


def shutdown_import_queue_service():
    """Fährt den globalen ImportQueueService herunter."""
    global _import_queue_service

    if _import_queue_service is not None:
        _import_queue_service.stop()
        _import_queue_service = None
