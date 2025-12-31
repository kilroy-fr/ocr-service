"""
Main Routes - Index page and event streaming
"""
import os
import json
import queue
import time
from flask import Blueprint, render_template, request, Response, session

from services.logger import log, ui_log_queue
from services.session_manager import ensure_staging, registry
from services.file_utils import fs, cleanup_orphaned_files
from config import (
    DATA_FOLDER, INPUT_ROOT, JSON_FOLDER, MODEL_LLM1
)

main_bp = Blueprint('main', __name__)


def event_stream():
    """Server-Sent Events Stream für Live-Logs."""
    log("📄 OCR-Service wurde gestartet.")
    yield f"data: Verbunden mit Server...\n\n"
    while True:
        try:
            message = ui_log_queue.get(timeout=1)

            # Bereinige von Surrogates
            try:
                clean_message = message.encode('utf-8', errors='replace').decode('utf-8')
            except:
                clean_message = "Log-Nachricht konnte nicht encodiert werden"

            yield f"data: {clean_message}\n\n"
        except queue.Empty:
            time.sleep(0.1)


@main_bp.route("/stream")
def stream():
    """Event-Stream Endpoint für Live-Updates."""
    return Response(event_stream(), mimetype="text/event-stream")


@main_bp.route('/')
def index():
    """Hauptseite mit Dateiliste."""
    session_id = ensure_staging()

    # Alte control.json dieser Session löschen
    control_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")
    if os.path.exists(control_path):
        try:
            os.remove(control_path)
            log(f"🗑️ Session-spezifische control.json gelöscht: {control_path}")
        except Exception as e:
            log(f"⚠️ Fehler beim Löschen der Datei: {e}", level="warning")

    # Alte Sessions aufräumen
    try:
        stale = registry.cleanup_stale_sessions(timeout_minutes=30)
        if stale:
            from pathlib import Path
            active = registry.get_active_sessions(timeout_minutes=30)
            stats = cleanup_orphaned_files(Path(fs.work_root), Path(fs.output_root), active)
            log(f"🧹 {len(stale)} abgelaufene Sessions aufgeräumt: {stats['work_dirs_removed']} Verzeichnisse")
    except Exception as e:
        log(f"⚠️ Cleanup-Fehler (nicht kritisch): {e}", level="warning")

    # processed_files für neue Session initialisieren
    if "processed_files" not in session:
        session["processed_files"] = {}

    # Error-Handling
    error_code = request.args.get("error")
    error_msg = None
    if error_code == "keine_datei":
        error_msg = "⚠️ Bitte mindestens eine Datei auswählen."

    # Subdirs scannen (falls benötigt)
    subdirs = [os.path.relpath(os.path.join(dp, d), DATA_FOLDER)
               for dp, dn, _ in os.walk(DATA_FOLDER) for d in dn]

    # Medidok-Dateien laden
    medidok_files = []
    medidok_dir = INPUT_ROOT

    log(f"📂 Suche Dateien in: {medidok_dir}")

    if os.path.exists(medidok_dir):
        try:
            from PIL import Image

            all_files = os.listdir(medidok_dir)
            log(f"📂 Gefundene Dateien gesamt: {len(all_files)}")

            # Alle unterstützten Dateien sammeln (inkl. TIF)
            supported_files = [
                f for f in all_files
                if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'))
            ]

            medidok_files = []

            for filename in supported_files:
                file_path = os.path.join(medidok_dir, filename)

                # ✅ TIF/TIFF automatisch zu JPG konvertieren
                if filename.lower().endswith(('.tif', '.tiff')):
                    try:
                        log(f"🔄 Konvertiere TIF zu JPG: {filename}")
                        img = Image.open(file_path)

                        # Erste Seite bei Multi-Page TIFF
                        if hasattr(img, 'n_frames') and img.n_frames > 1:
                            img.seek(0)

                        # RGB konvertieren für JPG
                        if img.mode not in ('RGB', 'L'):
                            img = img.convert('RGB')

                        # Neuer JPG-Dateiname
                        base_name = os.path.splitext(filename)[0]
                        jpg_name = base_name + '.jpg'
                        jpg_path = os.path.join(medidok_dir, jpg_name)

                        # Als JPG speichern
                        img.save(jpg_path, 'JPEG', quality=95)
                        img.close()

                        # Original TIF löschen
                        os.remove(file_path)

                        log(f"✅ TIF zu JPG konvertiert und Original gelöscht: {jpg_name}")
                        medidok_files.append(jpg_name)
                    except Exception as e:
                        log(f"❌ Fehler bei TIF-Konvertierung {filename}: {e}", level="error")
                        # Bei Fehler: Original behalten
                        medidok_files.append(filename)
                else:
                    medidok_files.append(filename)

            log(f"✅ Gefilterte PDF/Bild-Dateien: {len(medidok_files)}")
            if medidok_files:
                log(f"   Beispiele: {medidok_files[:5]}")

        except Exception as e:
            log(f"❌ Fehler beim Lesen von {medidok_dir}: {e}", level="error")
    else:
        log(f"❌ Verzeichnis nicht gefunden: {medidok_dir}", level="error")

    public_src = "/M" + INPUT_ROOT[6:]

    # Verarbeitete Dateien an Template übergeben
    processed_files = session.get("processed_files", {})

    # Aktuelles Modell an Template übergeben
    current_model = session.get("selected_model", MODEL_LLM1)

    return render_template(
        "index.html",
        error=error_msg,
        medidok_files=medidok_files,
        subdirs=subdirs,
        llm=current_model,
        current_model=current_model,
        med_src=public_src,
        processed_files=json.dumps(processed_files)
    )
