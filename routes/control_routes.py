"""
Control Routes - Document Control Panel
"""
import os
import json
import time
import fitz
from datetime import datetime
from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for

from services.logger import log
from services.session_manager import ensure_staging, cleanup_session, registry
from services.file_utils import (
    fs, handle_successful_processing, sanitize_filename,
    cleanup_orphaned_files, _os_rename_original
)
from services.ollama_client import warmup_ollama
from services.import_queue import get_import_queue_service
from config import (
    JSON_FOLDER, INPUT_ROOT, OUTPUT_ROOT, WORK_ROOT,
    IMPORT_MEDIDOK, TRASH_DIR, MODEL_LLM1
)

control_bp = Blueprint('control', __name__)


@control_bp.route("/control", methods=["GET"])
def control():
    """Control-Panel Hauptansicht."""
    session_id = session.get("session_id", "default")
    json_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")
    if not os.path.exists(json_path):
        return "❌ Keine Analysedaten gefunden. Bitte führen Sie zuerst eine Analyse durch.", 400

    with open(json_path, "r") as f:
        control_data = json.load(f)

    index = int(request.args.get("index", 0))
    if index < 0 or index >= len(control_data):
        return "❌ Ungültiger Index", 400

    return render_template("control.html",
                           files=control_data,
                           index=index)


@control_bp.route("/get_control_data", methods=["GET"])
def get_control_data():
    """
    Liefert die aktuelle control.json für sukzessives Nachladen.
    """
    session_id = session.get("session_id", "default")
    json_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")

    if not os.path.exists(json_path):
        return jsonify(success=False, message="Keine Daten verfügbar"), 404

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            control_data = json.load(f)

        return jsonify(success=True, data=control_data, count=len(control_data))
    except Exception as e:
        log(f"❌ Fehler beim Laden von control.json: {e}", level="error")
        return jsonify(success=False, message=str(e)), 500


@control_bp.route("/save_control_data", methods=["POST"])
def save_control_data():
    """Speichert Änderungen in control.json."""
    session_id = session.get("session_id", "default")
    json_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")
    updated = request.get_json()
    index = updated.get("index")

    with open(json_path, "r") as f:
        data = json.load(f)

    # Aktualisiere den Eintrag
    if 0 <= index < len(data):
        # WICHTIG: originalFilename NIEMALS überschreiben!
        original_filename = data[index].get("originalFilename")

        data[index]["name"] = updated["name"]
        data[index]["vorname"] = updated["vorname"]
        data[index]["geburtsdatum"] = updated["geburtsdatum"]
        data[index]["datum"] = updated["datum"]
        data[index]["beschreibung1"] = updated["beschreibung1"]
        data[index]["beschreibung2"] = updated["beschreibung2"]
        data[index]["categoryID"] = updated["categoryID"]
        data[index]["selected"] = updated["selected"]

        # originalFilename explizit erhalten
        if original_filename:
            data[index]["originalFilename"] = original_filename

        with open(json_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return jsonify(success=True)
    return jsonify(success=False), 400


@control_bp.route("/rename_file", methods=["POST"])
def rename_file():
    """Benennt Datei nach Kanon-Schema um."""
    data = request.get_json(force=True) or {}
    old_rel = data.get("old_filename")
    if not old_rel:
        return jsonify(success=False, message="Fehlender Dateiname."), 400

    # control_<session>.json laden
    session_id = session.get("session_id", "default")
    json_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")
    if not os.path.exists(json_path):
        return jsonify(success=False, message="Keine Kontroll-Daten vorhanden."), 400

    with open(json_path, "r", encoding="utf-8") as f:
        control_data = json.load(f)

    # Eintrag suchen
    entry = next((e for e in control_data if str(e.get("file", "")) == str(old_rel)), None)
    if not entry:
        return jsonify(success=False, message="Eintrag nicht gefunden."), 404

    # Zielnamen nach Kanon-Schema bestimmen
    result = handle_successful_processing(
        summary_data=entry,
        original_path=old_rel,
        target_dir=os.path.dirname(old_rel) if "/" in old_rel else ""
    )
    new_base_presan = result["renamed"]
    new_base = sanitize_filename(new_base_presan)
    new_rel = os.path.join(os.path.dirname(old_rel), new_base) if "/" in old_rel else new_base

    # Eintrag in control.json aktualisieren
    for e in control_data:
        if str(e.get("file", "")) == str(old_rel):
            e["file"] = new_rel
            e["filename"] = os.path.basename(new_rel)
            break

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(control_data, f, ensure_ascii=False, indent=2)

    return jsonify(success=True, new_filename=new_rel)


@control_bp.route("/finalize_import", methods=["POST"])
def finalize_import():
    """Finalisiert Import: Commit + Verschieben nach IMPORT_MEDIDOK."""
    payload = request.get_json(force=True) or {}
    entries = payload.get("files", [])
    if not entries:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400

    sid = session.get("session_id")

    # TRASH-Verzeichnis mit Zeitstempel erstellen
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_session_dir = os.path.join(TRASH_DIR, f"session_{sid}_{timestamp}")
    os.makedirs(trash_session_dir, exist_ok=True)
    log(f"📦 TRASH-Ordner erstellt: {trash_session_dir}")

    # 1) Commit durchführen
    try:
        fs.commit()
        log(f"✅ Commit erfolgreich für Session: {sid}")
    except Exception as e:
        log(f"❌ Commit fehlgeschlagen: {e}", level="error")
        return jsonify(success=False, message=f"Commit fehlgeschlagen: {e}"), 500

    # 2) Dateien sequenziell über ImportQueue nach IMPORT_MEDIDOK verschieben
    os.makedirs(IMPORT_MEDIDOK, exist_ok=True)
    moved = 0
    queued = 0
    trashed = 0
    original_files_to_trash = set()

    files_to_copy = [e for e in entries if bool(e.get("include")) and e.get("file")]
    total_files = len(files_to_copy)

    log(f"📄 Starte sequenziellen Import von {total_files} Dateien...")

    # ImportQueue-Service holen
    import_queue = get_import_queue_service(IMPORT_MEDIDOK)

    for idx, entry in enumerate(files_to_copy, 1):
        rel_name = entry.get("file")
        original_filename = entry.get("originalFilename")

        log(f"📄 Reihe Datei {idx}/{total_files} ein: {os.path.basename(rel_name)}")

        # Verarbeitete Datei aus OUTPUT_ROOT
        src = os.path.join(OUTPUT_ROOT, rel_name)
        if not os.path.exists(src):
            alt = os.path.join(OUTPUT_ROOT, os.path.basename(rel_name))
            if os.path.exists(alt):
                src = alt
            else:
                log(f"[WARN] finalize_import: Quelle nicht gefunden: {src}")
                continue

        # In Import-Queue einreihen (wird sequenziell verarbeitet)
        filename = os.path.basename(rel_name)
        if import_queue.enqueue_file(src, filename, sid):
            queued += 1
            moved += 1  # Zählt als "verschoben" sobald in Queue
            log(f"✅ In Import-Queue eingereiht: {filename}")
        else:
            log(f"❌ Fehler beim Einreihen: {filename}", level="error")

        # Original-Dateinamen für TRASH sammeln
        if original_filename:
            original_files_to_trash.add(original_filename)

    # 3) Original-Dateien in TRASH verschieben
    for original_filename in original_files_to_trash:
        original_path = os.path.join(INPUT_ROOT, original_filename)

        if os.path.exists(original_path):
            trash_path = os.path.join(trash_session_dir, original_filename)
            os.makedirs(os.path.dirname(trash_path), exist_ok=True)

            try:
                # Verwende originale os.rename (umgeht Staging-Patch)
                _os_rename_original(original_path, trash_path)
                trashed += 1
                log(f"🗑️ Original in TRASH: {original_filename}")
            except Exception as e:
                log(f"⚠️ Fehler beim Verschieben nach TRASH: {original_filename} - {e}", level="warning")
        else:
            log(f"[WARN] Original nicht gefunden in INPUT_ROOT: {original_filename}")

    # 4) Session aufräumen
    if sid:
        registry.unregister(sid)
        log(f"🧹 Session nach Finalisierung aufgeräumt: {sid}")

    session.clear()

    log(f"📊 Zusammenfassung: {queued} Dateien in Queue eingereiht, {trashed} Originale in TRASH verschoben")
    log(f"ℹ️ Die Dateien werden nun sequenziell verarbeitet. Nutzen Sie /import_queue_status zur Überwachung.")

    return jsonify(
        success=True,
        queued=queued,
        moved=moved,
        trashed=trashed,
        trash_location=trash_session_dir,
        message=f"{queued} Dateien werden sequenziell importiert. Der externe Dienst erhält jeweils nur eine Datei."
    )


@control_bp.route("/combine_medidok", methods=["POST"])
def combine_medidok_route():
    """Kombiniert mehrere PDFs zu einer Datei."""
    session_id = ensure_staging()
    data = request.get_json(force=True) or {}
    selected_files = data.get("files", [])

    if not selected_files:
        return jsonify(success=False, message="Keine Dateien ausgewählt."), 400

    log(f"🧩 combine_medidok gestartet mit {len(selected_files)} Dateien")

    try:
        # Pfade auflösen
        resolved_paths = []
        for filename in selected_files:
            staging_path = os.path.join(fs.work_dir, filename)
            if os.path.exists(staging_path):
                resolved_paths.append(staging_path)
                continue

            input_path = os.path.join(INPUT_ROOT, filename)
            if os.path.exists(input_path):
                resolved_paths.append(input_path)
                continue

            raise FileNotFoundError(f"Datei nicht gefunden: {filename}")

        if len(resolved_paths) < 2:
            raise ValueError("Mindestens 2 Dateien erforderlich zum Kombinieren")

        # Kombinieren mit PyMuPDF
        combined_pdf = fitz.open()

        for path in resolved_paths:
            with fitz.open(path) as pdf:
                combined_pdf.insert_pdf(pdf)

        # Ausgabedateiname
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"combined_{timestamp}.pdf"
        out_path = os.path.join(fs.work_dir, out_name)

        combined_pdf.save(out_path)
        combined_pdf.close()

        log(f"✅ PDF kombiniert: {out_name} ({len(resolved_paths)} Dateien)")

        # Als verarbeitet markieren
        if "processed_files" not in session:
            session["processed_files"] = {}

        for file in selected_files:
            session["processed_files"][file] = {
                "operation": "merged",
                "timestamp": time.time(),
                "result": out_name
            }
        session.modified = True

        return jsonify(
            success=True,
            combined=out_name,
            processed_files=selected_files
        )

    except Exception as e:
        log(f"❌ combine_medidok: {e}")
        return jsonify(success=False, message=str(e)), 500


@control_bp.route("/split_pdf", methods=["POST"])
def split_pdf_route():
    """Zerlegt eine PDF in einzelne Seiten."""
    session_id = ensure_staging()
    data = request.get_json(force=True) or {}
    filename = data.get("file")

    if not filename:
        return jsonify(success=False, message="Keine Datei übergeben."), 400

    log(f"🔪 split_pdf gestartet für: {filename}")

    try:
        # Pfad auflösen
        source_path = None

        staging_path = os.path.join(fs.work_dir, filename)
        if os.path.exists(staging_path):
            source_path = staging_path
        else:
            input_path = os.path.join(INPUT_ROOT, filename)
            if os.path.exists(input_path):
                source_path = input_path

        if not source_path:
            raise FileNotFoundError(f"Datei nicht gefunden: {filename}")

        if not filename.lower().endswith('.pdf'):
            raise ValueError("Nur PDF-Dateien können zerlegt werden")

        # PDF splitten
        doc = fitz.open(source_path)

        created_files = []
        base_name = os.path.splitext(filename)[0]

        for page_num in range(len(doc)):
            single_page = fitz.open()
            single_page.insert_pdf(doc, from_page=page_num, to_page=page_num)

            page_filename = f"{base_name}_seite_{page_num+1:03d}.pdf"
            page_path = os.path.join(fs.work_dir, page_filename)

            single_page.save(page_path)
            single_page.close()

            created_files.append(page_filename)

        doc.close()

        # Als verarbeitet markieren
        if "processed_files" not in session:
            session["processed_files"] = {}

        session["processed_files"][filename] = {
            "operation": "split",
            "timestamp": time.time(),
            "result_count": len(created_files)
        }
        session.modified = True

        log(f"✅ split_pdf erfolgreich: {len(created_files)} Seiten erstellt")

        return jsonify(
            success=True,
            files=created_files,
            count=len(created_files),
            processed_file=filename
        )

    except Exception as e:
        log(f"❌ split_pdf: {e}")
        return jsonify(success=False, message=str(e)), 500


@control_bp.route("/mark_files_processed", methods=["POST"])
def mark_files_processed():
    """Markiert Dateien als verarbeitet."""
    data = request.get_json(force=True) or {}
    files = data.get("files", [])
    operation = data.get("operation", "unknown")

    if not files:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400

    if "processed_files" not in session:
        session["processed_files"] = {}

    for file in files:
        session["processed_files"][file] = {
            "operation": operation,
            "timestamp": time.time()
        }

    session.modified = True
    log(f"🔒 {len(files)} Dateien als {operation} markiert")

    return jsonify(success=True, marked=len(files))


@control_bp.route("/get_processed_files", methods=["GET"])
def get_processed_files():
    """Gibt Liste der verarbeiteten Dateien zurück."""
    processed = session.get("processed_files", {})
    return jsonify(success=True, processed_files=processed)


@control_bp.route("/commit", methods=["POST"])
def commit_changes():
    """Führt Commit aus."""
    try:
        fs.commit()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500


@control_bp.route("/abort", methods=["POST"])
def abort_changes():
    """Verwirft alle Änderungen."""
    try:
        sid = session.get("session_id")

        # Staging abräumen
        fs.abort()
        log(f"🚫 Änderungen verworfen für Session: {sid}")

        # Session aufräumen
        cleanup_session()
        session.clear()

        return jsonify(success=True)
    except Exception as e:
        log(f"❌ Fehler beim Verwerfen: {e}", level="error")
        return jsonify(success=False, message=str(e)), 500


@control_bp.route("/reset_session")
def reset_session():
    """Setzt Session zurück."""
    old_sid = session.get("session_id")

    try:
        # Altes Staging abräumen
        if fs.session_id:
            fs.abort()
            log(f"🧹 Staging für alte Session abgeräumt: {fs.session_id}")

        # Alte Session aus Registry entfernen
        if old_sid:
            registry.unregister(old_sid)
            log(f"🗑️ Session aus Registry entfernt: {old_sid}")

    except Exception as e:
        log(f"⚠️ Fehler beim Session-Reset: {e}", level="warning")

    # Flask-Session clearen
    session.clear()

    log(f"🔄 Session-Reset abgeschlossen")

    return redirect(url_for("main.index"))


@control_bp.route("/import_queue_status", methods=["GET"])
def import_queue_status():
    """
    Gibt den aktuellen Status der Import-Queue zurück.

    Ermöglicht Überwachung des sequenziellen Import-Prozesses.
    """
    try:
        import_queue = get_import_queue_service(IMPORT_MEDIDOK)
        stats = import_queue.get_stats()

        return jsonify(
            success=True,
            stats=stats
        )
    except Exception as e:
        log(f"❌ Fehler beim Abrufen des Queue-Status: {e}", level="error")
        return jsonify(success=False, message=str(e)), 500
