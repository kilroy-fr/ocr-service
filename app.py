import sys
import os

# Fix für Windows-Netzlaufwerk Encoding
if sys.platform.startswith('linux'):
    import locale

    # Setze explizit UTF-8
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['LC_ALL'] = 'de_DE.UTF-8'
    os.environ['LANG'] = 'de_DE.UTF-8'

    try:
        locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')
    except:
        pass

from flask import Flask, session, current_app, request
from pathlib import Path

from services.logger import log
from services.session_manager import registry, update_session_activity
from services.file_utils import fs, to_rel_under_input, cleanup_old_json_files, cleanup_orphaned_files
from services.import_queue import get_import_queue_service, shutdown_import_queue_service
from config import (
    UPLOAD_FOLDER, INPUT_ROOT, OUTPUT_ROOT, WORK_ROOT,
    IMPORT_MEDIDOK, FAIL_DIR_MEDIDOK, LOGGING_FOLDER, JSON_FOLDER,
    TRASH_DIR, MODEL_LLM1
)

# Flask App initialisieren
app = Flask(__name__)
app.secret_key = "REDACTED"

# Flask Konfiguration für UTF-8 / Umlaute
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# Jinja2 Templates UTF-8
app.jinja_env.globals.update(str=str)

# Verzeichnisse erstellen
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# OS-Patching für Staging (Plan-Modus)
import os as _os_patch

# Originale OS-Funktionen speichern (für direkten Zugriff ohne Staging)
_os_rename_real = _os_patch.rename
_os_remove_real = _os_patch.remove

# Exportiere für andere Module
os_remove_real = _os_remove_real
os_rename_real = _os_rename_real


def _plan_rename(src, dst):
    """Geplantes Rename - wird ins Staging-Manifest geschrieben."""
    src_rel = to_rel_under_input(src)
    dst_rel = to_rel_under_input(dst)
    if src_rel and dst_rel:
        fs.plan_rename(src_rel, dst_rel)
        log(f"[PLAN] rename {src_rel} -> {dst_rel}")
    else:
        log(f"[BYPASS] rename outside INPUT_ROOT: {src} -> {dst}")


def _plan_delete(path):
    """Geplantes Delete - wird ins Staging-Manifest geschrieben."""
    rel = to_rel_under_input(path)
    if rel:
        fs.plan_delete(rel)
        log(f"[PLAN] delete {rel}")
    else:
        log(f"[BYPASS] remove outside INPUT_ROOT: {path}")


# OS-Funktionen patchen
_os_patch.rename = _plan_rename
_os_patch.remove = _plan_delete
_os_patch.unlink = _plan_delete  # unlink ist Alias für remove


# Flask Hooks
@app.after_request
def after_request_hook(response):
    """Aktualisiert Session-Aktivität nach jedem Request."""
    update_session_activity()
    return response


@app.before_request
def before_request_hook():
    """Stellt sicher, dass Session-Defaults gesetzt sind, inkl. Modell aus Cookie."""

    # Cookie-basierte Modellauswahl laden
    if "selected_model" not in session:
        cookie_model = request.cookies.get("selected_model")
        if cookie_model:
            session["selected_model"] = cookie_model
            log(f"📋 Modell aus Cookie geladen: {cookie_model}")
        else:
            # Fallback: Erstes verfügbares Modell oder CONFIG-Default
            session["selected_model"] = current_app.config.get("DEFAULT_MODEL", MODEL_LLM1)
            log(f"🔧 Fallback-Modell gesetzt: {session['selected_model']}")

    # Weitere Defaults
    session.setdefault("temperature", current_app.config.get("DEFAULT_TEMPERATURE", 0.2))
    session.setdefault("prompt_template", current_app.config.get("PROMPT_TEMPLATE", ""))


# Routen registrieren
from routes import register_routes
register_routes(app)


# Verzeichnisse sicherstellen
def ensure_directories():
    """Stellt sicher, dass alle benötigten Verzeichnisse existieren."""
    # Lokale Verzeichnisse, die wir erstellen UND testen können
    local_dirs = [
        UPLOAD_FOLDER,
        WORK_ROOT,
        IMPORT_MEDIDOK,
        FAIL_DIR_MEDIDOK,
        LOGGING_FOLDER,
        JSON_FOLDER
    ]

    # Netzlaufwerk-Verzeichnisse: nur erstellen, KEIN Schreibtest
    network_dirs = [
        INPUT_ROOT,
        OUTPUT_ROOT,
        TRASH_DIR
    ]

    # Lokale Verzeichnisse: erstellen + Schreibtest
    for dir_path in local_dirs:
        try:
            os.makedirs(dir_path, exist_ok=True)

            # Schreibtest
            test_file = os.path.join(dir_path, ".write_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            log(f"✅ Verzeichnis OK (lokal): {dir_path}")

        except Exception as e:
            log(f"❌ Fehler bei lokalem Verzeichnis {dir_path}: {e}", level="error")

    # Netzlaufwerk-Verzeichnisse: nur erstellen, kein Test
    for dir_path in network_dirs:
        try:
            os.makedirs(dir_path, exist_ok=True)
            log(f"✅ Verzeichnis erstellt (Netzlaufwerk): {dir_path}")
        except Exception as e:
            log(f"⚠️ Konnte Verzeichnis nicht erstellen: {dir_path} - {e}", level="warning")

    # INPUT_ROOT: Dateien zählen (nur lesen)
    if os.path.exists(INPUT_ROOT):
        try:
            all_items = os.listdir(INPUT_ROOT)
            files = [f for f in all_items
                    if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'))]
            log(f"🔍 INPUT_ROOT ({INPUT_ROOT}): {len(files)} verarbeitbare Dateien")
            if files:
                log(f"   Beispiele: {', '.join(files[:5])}")
            else:
                log(f"   ⚠️ Keine PDF/Bild-Dateien im Verzeichnis!", level="warning")
        except Exception as e:
            log(f"❌ Fehler beim Lesen von INPUT_ROOT: {e}", level="error")
    else:
        log(f"❌ INPUT_ROOT existiert nicht: {INPUT_ROOT}", level="error")
        log(f"   → Prüfen Sie das Docker-Volume: /mnt/m:/app/medidok", level="error")


def startup_cleanup():
    """Führt beim Start ein vollständiges Cleanup durch."""
    log("🧹 Starte Startup-Cleanup...")

    try:
        # 1. Alte control.json Dateien löschen (älter als 1 Tag)
        cleanup_old_json_files(JSON_FOLDER, days_old=1)

        # 2. SessionRegistry komplett zurücksetzen
        if registry.registry_path.exists():
            registry.registry_path.unlink()
            log("🗑️ Alte Session-Registry gelöscht (Server-Neustart)")
            registry._save({})

        # 3. Alle verwaisten Dateien aufräumen
        stats = cleanup_orphaned_files(
            Path(WORK_ROOT),
            Path(OUTPUT_ROOT),
            set()  # Leeres Set = keine aktiven Sessions
        )

        log(f"🧹 Cleanup-Statistik:")
        log(f"   - Work-Verzeichnisse: {stats['work_dirs_removed']}")
        log(f"   - Work-Dateien: {stats['work_files_removed']}")
        log(f"   - Staging-Dateien: {stats['staging_files_removed']}")

        if stats['errors']:
            log(f"⚠️ Cleanup-Fehler: {len(stats['errors'])}")
            for err in stats['errors'][:5]:
                log(f"   - {err}", level="warning")

        log("✅ Startup-Cleanup abgeschlossen")

    except Exception as e:
        log(f"❌ Fehler beim Startup-Cleanup: {e}", level="error")
        import traceback
        log(traceback.format_exc(), level="error")


if __name__ == '__main__':
    ensure_directories()
    startup_cleanup()

    # ImportQueue-Service initialisieren und starten
    log("🔄 Initialisiere ImportQueue-Service...")
    try:
        import_queue = get_import_queue_service(IMPORT_MEDIDOK)
        log("✅ ImportQueue-Service gestartet")
    except Exception as e:
        log(f"❌ Fehler beim Starten des ImportQueue-Service: {e}", level="error")

    try:
        # Debug-Modus für Hot-Reload während Entwicklung
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)
    finally:
        # Sauberes Herunterfahren des ImportQueue-Service
        log("🛑 Fahre ImportQueue-Service herunter...")
        shutdown_import_queue_service()
