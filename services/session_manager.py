"""
Session Manager Module
Handles Flask session management and staging initialization
"""
import uuid
from pathlib import Path
from flask import session
from services.logger import log
from services.file_utils import SessionRegistry, fs
from config import WORK_ROOT


# SessionRegistry initialisieren
registry = SessionRegistry(Path(WORK_ROOT) / "sessions.json")


def ensure_staging():
    """Stellt sicher, dass eine Session existiert und registriert ist."""
    sid = session.get("session_id")

    if not sid:
        # Neue Session erstellen
        sid = str(uuid.uuid4())
        session["session_id"] = sid
        registry.register(sid)
        log(f"🆕 Neue Session erstellt: {sid}")
    else:
        # Bestehende Session aktivieren
        registry.update_activity(sid)
        log(f"♻️ Session reaktiviert: {sid}")

    if not fs.session_id or fs.session_id != sid:
        # Staging starten (räumt automatisch altes Staging auf)
        fs.start(sid)
        log(f"🧹 Staging für Session {sid} initialisiert")

    return sid


def update_session_activity():
    """Aktualisiert Session-Aktivität nach jedem Request."""
    if fs.session_id:
        try:
            registry.update_activity(fs.session_id)
        except Exception:
            pass


def cleanup_session(session_id=None):
    """Räumt eine Session auf (optional mit spezifischer ID)."""
    sid = session_id or session.get("session_id")

    try:
        # Altes Staging abräumen
        if fs.session_id:
            fs.abort()
            log(f"🧹 Staging für Session abgeräumt: {fs.session_id}")

        # Session aus Registry entfernen
        if sid:
            registry.unregister(sid)
            log(f"🗑️ Session aus Registry entfernt: {sid}")

    except Exception as e:
        log(f"⚠️ Fehler beim Session-Cleanup: {e}", level="warning")
