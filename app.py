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

from flask import Flask, request, render_template, send_from_directory, abort, Response, stream_with_context, redirect, url_for, jsonify, session, current_app
from services.logger import log_queue, log, ui_log_queue
from services.ollama_client import warmup_ollama
from services.ocr import (
    process_medidok_files, 
    process_medidok_files_with_model,  # NEU für Background-Thread
    create_control_json_from_summaries
)
from services.file_utils import (
    fs, to_rel_under_input,
    merge_images_to_pdf, timestamped_pdf_name,
    handle_successful_processing, cleanup_old_json_files,
    clear_folder, combine_and_delete, sanitize_filename,
    split_pdf_to_pages,
)
from config import (
  UPLOAD_FOLDER, PROCESSED_FOLDER, DATA_FOLDER,
  INPUT_ROOT, OUTPUT_ROOT, WORK_ROOT, TRASH_DIR,
  SOURCE_DIR_MEDIDOK, TARGET_DIR_MEDIDOK,
  IMPORT_MEDIDOK, OLLAMA_URL, MODEL_LLM1, JSON_FOLDER
)
from werkzeug.utils import secure_filename
from collections import defaultdict

import threading
import tempfile
import uuid
import queue
import time
import json
import shutil
import requests
import os as _os_patch
import subprocess  # NEU: Für OCR-Only Funktion
import img2pdf     # NEU: Für Bild-zu-PDF Konvertierung

from queue import Queue
from typing import Dict, List

# Globaler Status-Tracker für progressive Analysen
analysis_status: Dict[str, dict] = {}
analysis_lock = threading.Lock()

_os_rename_real = _os_patch.rename
_os_remove_real = _os_patch.remove

# SessionRegistry initialisieren
from pathlib import Path
from services.file_utils import SessionRegistry, cleanup_orphaned_files

app = Flask(__name__)
app.secret_key = "REDACTED"
registry = SessionRegistry(Path(WORK_ROOT) / "sessions.json")

# Flask Konfiguration für UTF-8 / Umlaute
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# Jinja2 Templates UTF-8
app.jinja_env.globals.update(str=str)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

def get_log_snapshot():
    logs = []
    try:
        while True:
            logs.append(ui_log_queue.get_nowait())
    except queue.Empty:
        pass
    return "\n".join(logs)

def event_stream():
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

def _plan_rename(src, dst):
    src_rel = to_rel_under_input(src)
    dst_rel = to_rel_under_input(dst)
    if src_rel and dst_rel:
        fs.plan_rename(src_rel, dst_rel)
        log(f"[PLAN] rename {src_rel} -> {dst_rel}")
    else:
        log(f"[BYPASS] rename outside INPUT_ROOT: {src} -> {dst}")

def _plan_delete(path):
    rel = to_rel_under_input(path)
    if rel:
        fs.plan_delete(rel)
        log(f"[PLAN] delete {rel}")
    else:
        log(f"[BYPASS] remove outside INPUT_ROOT: {path}")

_os_patch.rename = _plan_rename
_os_patch.remove = _plan_delete

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

def background_analyze_files(session_id: str, file_paths: List[str], model: str, start_index: int = 1):
    """
    Analysiert Dateien im Hintergrund ab start_index.
    Die erste Datei (Index 0) wurde bereits im Hauptthread analysiert.
    
    Args:
        session_id: Flask Session-ID
        file_paths: Liste aller Dateipfade
        model: LLM-Modell (explizit übergeben, da kein Request-Context)
        start_index: Ab welchem Index soll analysiert werden
    """
    from services.ocr import process_medidok_files_with_model
    import os
    
    log(f"🔄 Background-Analyse gestartet für Session {session_id}: {len(file_paths) - start_index} Dateien")
    log(f"   Modell: {model}")
    
    with analysis_lock:
        analysis_status[session_id] = {
            'total': len(file_paths),
            'completed': start_index,
            'status': 'running',
            'errors': []
        }
    
    for i, file_path in enumerate(file_paths[start_index:], start=start_index):
        try:
            log(f"📄 Analysiere Datei {i+1}/{len(file_paths)}: {os.path.basename(file_path)}")
            
            # ✅ Thread-sichere Analyse MIT explizitem Modell (importiert aus ocr.py)
            results = process_medidok_files_with_model(
                [file_path], 
                OUTPUT_ROOT,
                model=model,
                session_id=session_id
            )
            
            if results:
                summary = results[0]["summary"]
                
                # An control.json anhängen MIT expliziter Session-ID
                create_control_json_from_summaries_explicit(
                    [summary], 
                    session_id=session_id,
                    overwrite=False,
                    dedupe=True
                )
                
                log(f"✅ Datei {i+1}/{len(file_paths)} fertig: {summary.get('filename', 'unknown')}")
            
            # Status aktualisieren
            with analysis_lock:
                if session_id in analysis_status:
                    analysis_status[session_id]['completed'] = i + 1
                    
        except Exception as e:
            log(f"❌ Fehler bei Datei {i+1}: {e}", level="error")
            import traceback
            log(traceback.format_exc(), level="error")
            with analysis_lock:
                if session_id in analysis_status:
                    analysis_status[session_id]['errors'].append(str(e))
    
    # Abschluss
    with analysis_lock:
        if session_id in analysis_status:
            analysis_status[session_id]['status'] = 'completed'
            log(f"✅ Background-Analyse abgeschlossen für Session {session_id}")


def create_control_json_from_summaries_explicit(summaries, session_id, *, overwrite=False, dedupe=True, key="file"):
    """
    Thread-sichere Version von create_control_json_from_summaries.
    Benötigt keine Flask Session (für Background-Threads).
    """
    path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")
    os.makedirs(JSON_FOLDER, exist_ok=True)

    # Basisdaten laden
    if not overwrite and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                control_data = json.load(f)
            if not isinstance(control_data, list):
                control_data = []
        except Exception:
            control_data = []
    else:
        control_data = []

    # Dedupe-Map aufbauen
    if dedupe and control_data:
        index = { str(entry.get(key, "")) : i for i, entry in enumerate(control_data) }
    else:
        index = {}

    # Neue Einträge einpflegen
    for s in summaries:
        entry = {
            "file": s.get("file",""),
            "filename": s.get("filename",""),
            "originalFilename": s.get("originalFilename", s.get("filename","")),
            "name": s.get("name",""),
            "vorname": s.get("vorname",""),
            "geburtsdatum": s.get("geburtsdatum",""),
            "datum": s.get("datum",""),
            "beschreibung1": s.get("beschreibung1",""),
            "beschreibung2": s.get("beschreibung2",""),
            "categoryID": s.get("categoryID",""),
            "selected": True,
        }
        k = str(entry.get(key, ""))
        if dedupe and k in index:
            control_data[index[k]] = entry  # überschreiben (neueste Werte)
        else:
            index[k] = len(control_data)
            control_data.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(control_data, f, ensure_ascii=False, indent=2)

    log(f"[INFO] control.json aktualisiert ({len(control_data)} Einträge): {path}")


@app.route("/copy_and_analyze", methods=["POST"])
def copy_and_analyze_progressive():
    """
    Progressive Analyse: Erste Datei sofort, Rest im Hintergrund.
    """
    log("🚀 /copy_and_analyze gestartet (progressiv)")
    session_id = ensure_staging()
    payload = request.get_json(force=True) or {}
    selected = payload.get("files", [])

    if selected and isinstance(selected[0], dict):
        selected = [x.get("file") for x in selected if x.get("file")]

    if not selected:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400

    # ✅ Modell aus Session holen (jetzt, solange wir im Request-Context sind)
    current_model = session.get("selected_model", MODEL_LLM1)
    log(f"🤖 Verwende Modell: {current_model}")

    warmup_ollama()

    # Pfade auflösen
    file_paths = []
    for name in selected:
        staging_path = os.path.join(fs.work_dir, name)
        if os.path.exists(staging_path):
            file_paths.append(staging_path)
            continue
        
        abs_path = os.path.join(INPUT_ROOT, name)
        if os.path.exists(abs_path):
            file_paths.append(abs_path)
            continue
        
        return jsonify(success=False, message=f"Datei nicht gefunden: {name}"), 404

    try:
        # ✅ ERSTE DATEI SOFORT ANALYSIEREN (normale Funktion, nutzt session)
        log(f"📄 Analysiere erste Datei: {os.path.basename(file_paths[0])}")
        first_result = process_medidok_files([file_paths[0]], OUTPUT_ROOT)
        
        if not first_result:
            return jsonify(success=False, message="Erste Datei konnte nicht analysiert werden"), 500
        
        first_summary = first_result[0]["summary"]
        
        # Control.json mit erster Datei erstellen
        create_control_json_from_summaries(
            [first_summary], 
            overwrite=True,
            dedupe=True
        )
        
        log(f"✅ Erste Datei fertig: {first_summary.get('filename', 'unknown')}")
        
        # ✅ RESTLICHE DATEIEN IM HINTERGRUND
        if len(file_paths) > 1:
            log(f"🔄 Starte Background-Analyse für {len(file_paths) - 1} weitere Dateien")
            
            # Session-ID UND Modell explizit übergeben für Background-Thread
            thread = threading.Thread(
                target=background_analyze_files,
                args=(session_id, file_paths, current_model, 1),  # model hinzugefügt
                daemon=True
            )
            thread.start()
            
            return jsonify(
                success=True, 
                progressive=True,
                total=len(file_paths),
                completed=1,
                model=current_model
            )
        else:
            # Nur eine Datei -> fertig
            return jsonify(success=True, progressive=False)
            
    except Exception as e:
        log(f"❌ Fehler in copy_and_analyze: {e}", level="error")
        import traceback
        log(traceback.format_exc(), level="error")
        return jsonify(success=False, message=str(e)), 500


@app.route("/analysis_status", methods=["GET"])
def get_analysis_status():
    """
    Gibt den aktuellen Analyse-Status für die Session zurück.
    """
    session_id = session.get("session_id")
    
    if not session_id:
        return jsonify(success=False, message="Keine Session gefunden"), 400
    
    with analysis_lock:
        status = analysis_status.get(session_id)
    
    if not status:
        # Keine laufende Analyse
        return jsonify(success=True, status='idle')
    
    return jsonify(
        success=True,
        status=status['status'],
        total=status['total'],
        completed=status['completed'],
        errors=status['errors']
    )


@app.route("/get_control_data", methods=["GET"])
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

@app.after_request
def update_session_activity(response):
    """Aktualisiert Session-Aktivität nach jedem Request."""
    if fs.session_id:
        try:
            registry.update_activity(fs.session_id)
        except Exception:
            pass
    return response
    
@app.before_request
def ensure_session_defaults():
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

        
@app.route("/control", methods=["GET"])
def control():
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

@app.route("/save_control_data", methods=["POST"])
def save_control_data():
    session_id = session.get("session_id", "default")
    json_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")        
    updated = request.get_json()
    index = updated.get("index")

    with open(json_path, "r") as f:
        data = json.load(f)

    # Aktualisiere den Eintrag
    if 0 <= index < len(data):
        # ✅ WICHTIG: originalFilename NIEMALS überschreiben!
        original_filename = data[index].get("originalFilename")
        
        data[index]["name"] = updated["name"]
        data[index]["vorname"] = updated["vorname"]
        data[index]["geburtsdatum"] = updated["geburtsdatum"]
        data[index]["datum"] = updated["datum"]
        data[index]["beschreibung1"] = updated["beschreibung1"]
        data[index]["beschreibung2"] = updated["beschreibung2"]
        data[index]["categoryID"] = updated["categoryID"]
        data[index]["selected"] = updated["selected"]
        
        # ✅ originalFilename explizit erhalten
        if original_filename:
            data[index]["originalFilename"] = original_filename

        with open(json_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return jsonify(success=True)
    return jsonify(success=False), 400
    
@app.route("/finalize_import", methods=["POST"])  
def finalize_import():
    payload = request.get_json(force=True) or {}
    entries = payload.get("files", [])
    if not entries:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400

    sid = session.get("session_id")
    
    # TRASH-Verzeichnis mit Zeitstempel erstellen
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_session_dir = os.path.join(TRASH_DIR, f"session_{sid}_{timestamp}")
    os.makedirs(trash_session_dir, exist_ok=True)
    log(f"📦 TRASH-Ordner erstellt: {trash_session_dir}")
    
    # 1) Commit durchführen (verschiebt Dateien von STAGING nach OUTPUT_ROOT)
    try:
        fs.commit()
        log(f"✅ Commit erfolgreich für Session: {sid}")
    except Exception as e:
        log(f"❌ Commit fehlgeschlagen: {e}", level="error")
        return jsonify(success=False, message=f"Commit fehlgeschlagen: {e}"), 500

    # 2) Dateien nach IMPORT_MEDIDOK verschieben und Originale in TRASH
    os.makedirs(IMPORT_MEDIDOK, exist_ok=True)
    moved = 0
    trashed = 0
    original_files_to_trash = set()  # Set um Duplikate zu vermeiden

    for entry in entries:
        rel_name = entry.get("file")
        include = bool(entry.get("include"))
        original_filename = entry.get("originalFilename")
       
        if not include or not rel_name:
            continue

        # Verarbeitete Datei aus OUTPUT_ROOT nach IMPORT_MEDIDOK verschieben
        src = os.path.join(OUTPUT_ROOT, rel_name)
        if not os.path.exists(src):
            # Versuche nur den Dateinamen (falls kein Unterverzeichnis)
            alt = os.path.join(OUTPUT_ROOT, os.path.basename(rel_name))
            if os.path.exists(alt):
                src = alt
            else:
                log(f"[WARN] finalize_import: Quelle nicht gefunden: {src}")
                continue

        dst = os.path.join(IMPORT_MEDIDOK, os.path.basename(rel_name))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        
        # ✅ Nach Commit: Verwende echte OS-Funktionen (nicht gepatcht)
        try:
            _os_rename_real(src, dst)
            moved += 1
            log(f"✅ Verschoben nach IMPORT: {os.path.basename(rel_name)}")
        except Exception as e:
            log(f"❌ Fehler beim Verschieben von {src}: {e}", level="error")
        
        # Original-Dateinamen für TRASH sammeln
        if original_filename:
            original_files_to_trash.add(original_filename)
    
    # 3) Original-Dateien aus INPUT_ROOT in TRASH verschieben
    for original_filename in original_files_to_trash:
        original_path = os.path.join(INPUT_ROOT, original_filename)
       
        if os.path.exists(original_path):
            trash_path = os.path.join(trash_session_dir, original_filename)
            
            # Unterverzeichnisse im TRASH erstellen falls nötig
            os.makedirs(os.path.dirname(trash_path), exist_ok=True)
            
            try:
                _os_rename_real(original_path, trash_path)
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
    
    log(f"📊 Zusammenfassung: {moved} Dateien importiert, {trashed} Originale in TRASH verschoben")
    
    return jsonify(
        success=True, 
        moved=moved, 
        trashed=trashed,
        trash_location=trash_session_dir
    )
    
@app.route("/mark_files_processed", methods=["POST"])
def mark_files_processed():
    """Markiert Dateien als verarbeitet (kombiniert oder gesplittet)."""
    data = request.get_json(force=True) or {}
    files = data.get("files", [])
    operation = data.get("operation", "unknown")  # "merged" oder "split"
    
    if not files:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400
    
    # In Session speichern
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

@app.route("/get_processed_files", methods=["GET"])
def get_processed_files():
    """Gibt Liste der verarbeiteten Dateien zurück."""
    processed = session.get("processed_files", {})
    return jsonify(success=True, processed_files=processed)
    
@app.route("/rename_file", methods=["POST"])
def rename_file():
    data = request.get_json(force=True) or {}
    old_rel = data.get("old_filename")
    if not old_rel:
        return jsonify(success=False, message="Fehlender Dateiname."), 400

    # 1) control_<session>.json laden und passenden Eintrag suchen
    session_id = session.get("session_id", "default")
    json_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")
    if not os.path.exists(json_path):
        return jsonify(success=False, message="Keine Kontroll-Daten vorhanden."), 400

    with open(json_path, "r", encoding="utf-8") as f:
        control_data = json.load(f)
    
    # Key ist in deiner control-Datei "file" (REL-Pfad)
    entry = next((e for e in control_data if str(e.get("file","")) == str(old_rel)), None)
    if not entry:
        return jsonify(success=False, message="Eintrag nicht gefunden."), 404

    # 2) Serverseitig den ZIELNAMEN nach dem Kanon-Schema bestimmen
    result = handle_successful_processing(
        summary_data=entry,
        original_path=old_rel,
        target_dir=os.path.dirname(old_rel) if "/" in old_rel else ""
    )
    new_base_presan = result["renamed"]
    new_base = sanitize_filename(new_base_presan)
    new_rel = os.path.join(os.path.dirname(old_rel), new_base) if "/" in old_rel else new_base

    # 3) Den Eintrag in control.json auf den neuen REL-Pfad umstellen
    for e in control_data:
        if str(e.get("file","")) == str(old_rel):
            e["file"] = new_rel
            e["filename"] = os.path.basename(new_rel)
            break
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(control_data, f, ensure_ascii=False, indent=2)

    return jsonify(success=True, new_filename=new_rel)

@app.route('/preview/<path:filename>')
def preview_file(filename):
    """Vorschau - einfach mit UTF-8 Mount."""
    from urllib.parse import unquote
    filename = unquote(filename)
    
    # Versuche zuerst im Staging
    if fs.session_id:
        staged = os.path.join(fs.work_dir, filename)
        if os.path.exists(staged):
            return send_from_directory(fs.work_dir, filename)
    
    # Fallback: Original im INPUT_ROOT
    return send_from_directory(INPUT_ROOT, filename)
    
@app.route('/')
def index():
    session_id = ensure_staging()
    
    # Alte control.json dieser Session löschen
    control_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")
    if os.path.exists(control_path):
        try:
            os.remove(control_path)
            log(f"🗑️ Session-spezifische control.json gelöscht: {control_path}")
        except Exception as e:
            log(f"⚠️ Fehler beim Löschen der Datei: {e}", level="warning")
    
    # WICHTIG: Alte Sessions aufräumen
    try:
        stale = registry.cleanup_stale_sessions(timeout_minutes=30)
        if stale:
            from services.file_utils import cleanup_orphaned_files
            active = registry.get_active_sessions(timeout_minutes=30)
            stats = cleanup_orphaned_files(fs.work_root, fs.output_root, active)
            log(f"🧹 {len(stale)} abgelaufene Sessions aufgeräumt: {stats['work_dirs_removed']} Verzeichnisse")
    except Exception as e:
        log(f"⚠️ Cleanup-Fehler (nicht kritisch): {e}", level="warning")
 
    # processed_files für neue Session initialisieren
    if "processed_files" not in session:
        session["processed_files"] = {}

    # Rest der Funktion bleibt gleich...
    error_code = request.args.get("error")
    error_msg = None
    if error_code == "keine_datei":
        error_msg = "⚠️ Bitte mindestens eine Datei auswählen."

    subdirs = [os.path.relpath(os.path.join(dp, d), DATA_FOLDER) 
               for dp, dn, _ in os.walk(DATA_FOLDER) for d in dn]

    medidok_files = []
    medidok_dir = INPUT_ROOT
    
    log(f"📂 Suche Dateien in: {medidok_dir}")
    
    if os.path.exists(medidok_dir):
        try:
            all_files = os.listdir(medidok_dir)
            log(f"📂 Gefundene Dateien gesamt: {len(all_files)}")
            
            medidok_files = [
                f for f in all_files
                if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png'))
            ]
            
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
    
    # WICHTIG: Aktuelles Modell an Template übergeben
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

@app.route('/processed/<path:filename>')
def serve_processed_file(filename):
    if fs.session_id:
        staged = os.path.join(fs.work_dir, filename)
        if os.path.exists(staged):
            return send_from_directory(fs.work_dir, filename)
    return send_from_directory(OUTPUT_ROOT, filename)

@app.route("/stream")
def stream():
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/upload', methods=['POST'])
def upload_files():
    """
    Einzel-Upload: Dateien NUR ins Staging kopieren (OHNE OCR/Analyse).
    OCR/Analyse erfolgt erst beim Klick auf "Analysieren!" (copy_and_analyze).
    """
    session_id = ensure_staging()
    
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        log("Keine Dateien ausgewählt")
        return jsonify(success=False, message="Keine Dateien ausgewählt"), 400

    # Dateien NUR ins Staging kopieren (kein OCR)
    uploaded_files = []
    for file in files:
        if file.filename:
            # Sichere den Dateinamen
            safe_name = secure_filename(file.filename)
            # Speichere direkt ins Staging-Verzeichnis
            staging_path = os.path.join(fs.work_dir, safe_name)
            file.save(staging_path)
            uploaded_files.append(safe_name)
            log(f"📤 Datei ins Staging kopiert: {safe_name}")

    if not uploaded_files:
        return jsonify(success=False, message="Keine Dateien hochgeladen"), 400

    log(f"✅ {len(uploaded_files)} Datei(en) ins Staging kopiert (ohne OCR)")
    return jsonify(success=True, files=uploaded_files, count=len(uploaded_files))

@app.route('/upload_folder', methods=['POST'])
def upload_folder():
    """
    Batch-Upload: Dateien NUR ins Staging kopieren (OHNE OCR/Analyse).
    OCR/Analyse erfolgt erst beim Klick auf "Analysieren!" (copy_and_analyze).
    """
    session_id = ensure_staging()

    uploaded_files = request.files.getlist("files")
    if not uploaded_files or all(f.filename == '' for f in uploaded_files):
        log("Keine Dateien empfangen")
        return jsonify(success=False, message="Keine Dateien empfangen"), 400

    # Alle Dateien sammeln (flach, ohne Ordnerstruktur)
    collected_files = []
    
    for file in uploaded_files:
        if not file.filename:
            continue
            
        # Nur Dateiname, keine Pfadstruktur
        filename = os.path.basename(file.filename)
        
        # Nur unterstützte Formate
        if not filename.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff')):
            log(f"⏭️ Überspringe Datei (nicht unterstützt): {filename}")
            continue
        
        # Sichere den Dateinamen
        safe_name = secure_filename(filename)
        
        # Bei Namenskonflikten: Präfix mit Timestamp
        staging_path = os.path.join(fs.work_dir, safe_name)
        if os.path.exists(staging_path):
            base, ext = os.path.splitext(safe_name)
            safe_name = f"{base}_{int(time.time())}{ext}"
            staging_path = os.path.join(fs.work_dir, safe_name)
        
        # Speichern
        file.save(staging_path)
        collected_files.append(safe_name)
        log(f"📤 Datei ins Staging kopiert: {safe_name}")

    if not collected_files:
        return jsonify(success=False, message="Keine verarbeitbaren Dateien gefunden"), 400

    log(f"📁 Batch-Upload: {len(collected_files)} Datei(en) ins Staging kopiert (ohne OCR)")
    return jsonify(success=True, files=collected_files, count=len(collected_files))

@app.route("/copy_and_analyze", methods=["POST"])
def copy_and_analyze():
    """
    Analysiert Dateien aus:
    - Medidok: INPUT_ROOT (Original-Dateien)
    - Einzel/Batch: Staging (bereits hochgeladene Dateien)
    
    Führt OCR + LLM-Analyse durch und erstellt control.json.
    """
    log("🚀 /copy_and_analyze gestartet")
    session_id = ensure_staging()
    payload = request.get_json(force=True) or {}
    selected = payload.get("files", [])

    # Strings oder Objekte akzeptieren
    if selected and isinstance(selected[0], dict):
        selected = [x.get("file") for x in selected if x.get("file")]

    if not selected:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400

    warmup_ollama()

    # Eingabepfade prüfen (Medidok: INPUT_ROOT, Einzel/Batch: Staging)
    file_paths = []
    for name in selected:
        # Zuerst im Staging suchen (Einzel/Batch)
        staging_path = os.path.join(fs.work_dir, name)
        if os.path.exists(staging_path):
            file_paths.append(staging_path)
            log(f"📂 Datei aus Staging: {name}")
            continue
        
        # Fallback: INPUT_ROOT (Medidok)
        abs_path = os.path.join(INPUT_ROOT, name)
        if os.path.exists(abs_path):
            file_paths.append(abs_path)
            log(f"📂 Datei aus INPUT_ROOT: {name}")
            continue
        
        # Nicht gefunden
        return jsonify(success=False, message=f"Datei nicht gefunden: {name}"), 404

    try:
        # Staging-sichere Verarbeitung + Summaries erzeugen
        results = process_medidok_files(file_paths, OUTPUT_ROOT)
        summaries = [r["summary"] for r in results]
        create_control_json_from_summaries(summaries, overwrite=True, dedupe=True)

        log(f"✅ /copy_and_analyze ok – {len(summaries)} Einträge")
        return jsonify(success=True)
    except Exception as e:
        log(f"❌ /copy_and_analyze Fehler: {e}", level="warning")
        return jsonify(success=False, message=str(e)), 500

@app.route("/available_models", methods=["GET"])
def available_models():
    try:
        response = requests.get(OLLAMA_URL.replace("/generate", "/tags"), timeout=5)
        response.raise_for_status()
        data = response.json()
        models = [model["name"] for model in data.get("models", [])]
        
        # Aktuell ausgewähltes Modell mitgeben
        current = session.get("selected_model")
        
        return jsonify(
            success=True, 
            models=models,
            current=current
        )
    except Exception as e:
        log(f"⚠️ Fehler beim Laden der Modelle: {e}", level="warning")
        # Fallback: mindestens CONFIG-Modelle zurückgeben
        return jsonify(
            success=True, 
            models=[MODEL_LLM1],
            current=session.get("selected_model", MODEL_LLM1),
            fallback=True
        )

@app.route("/set_model", methods=["POST"])
def set_model():
    model = request.json.get("model")
    if not model:
        return jsonify(success=False, message="Kein Modell angegeben"), 400
    
    # In Session speichern
    session["selected_model"] = model
    session.modified = True
    
    log(f"⚙️ Modell gewechselt: {model}")
    
    # Response mit Cookie setzen
    response = jsonify(success=True, model=model)
    response.set_cookie(
        "selected_model", 
        model, 
        max_age=31536000,  # 1 Jahr
        path="/",
        samesite="Lax"
    )
    return response

@app.route("/reset_session")
def reset_session():
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
    
    # Neue Session wird automatisch in ensure_staging() angelegt
    log(f"🔄 Session-Reset abgeschlossen, neue Session wird beim nächsten Request angelegt")
    
    return redirect(url_for("index"))

@app.route("/combine_medidok", methods=["POST"])
def combine_medidok_route():
    """
    Kombiniert Dateien aus INPUT_ROOT oder Staging.
    Unterstützt gemischte Quellen (Medidok + Einzel/Batch).
    """
    session_id = ensure_staging()
    data = request.get_json(force=True) or {}
    selected_files = data.get("files", [])
    
    if not selected_files:
        return jsonify(success=False, message="Keine Dateien ausgewählt."), 400

    log(f"🧩 combine_medidok gestartet mit {len(selected_files)} Dateien")
    log(f"   Dateien: {selected_files}")

    try:
        # Pfade auflösen: Staging ZUERST, dann INPUT_ROOT
        resolved_paths = []
        for filename in selected_files:
            # 1. Versuch: Im Staging
            staging_path = os.path.join(fs.work_dir, filename)
            if os.path.exists(staging_path):
                resolved_paths.append(staging_path)
                log(f"   ✓ Gefunden im Staging: {filename}")
                continue
            
            # 2. Versuch: Im INPUT_ROOT (Medidok)
            input_path = os.path.join(INPUT_ROOT, filename)
            if os.path.exists(input_path):
                resolved_paths.append(input_path)
                log(f"   ✓ Gefunden in INPUT_ROOT: {filename}")
                continue
            
            # Nicht gefunden
            raise FileNotFoundError(f"Datei nicht gefunden: {filename}")
        
        if len(resolved_paths) < 2:
            raise ValueError("Mindestens 2 Dateien erforderlich zum Kombinieren")
        
        # Kombinieren mit PyMuPDF
        import fitz
        combined_pdf = fitz.open()
        
        for path in resolved_paths:
            with fitz.open(path) as pdf:
                combined_pdf.insert_pdf(pdf)
        
        # Ausgabedateiname
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"combined_{timestamp}.pdf"
        out_path = os.path.join(fs.work_dir, out_name)
        
        combined_pdf.save(out_path)
        combined_pdf.close()
        
        log(f"✅ PDF kombiniert: {out_name} ({len(resolved_paths)} Dateien)")
        
        # Ursprungsdateien als verarbeitet markieren
        if "processed_files" not in session:
            session["processed_files"] = {}
        
        for file in selected_files:
            session["processed_files"][file] = {
                "operation": "merged",
                "timestamp": time.time(),
                "result": out_name
            }
        session.modified = True
        
        log(f"📌 Markierte Dateien: {selected_files}")
        
        return jsonify(
            success=True, 
            combined=out_name,
            processed_files=selected_files
        )
        
    except FileNotFoundError as e:
        log(f"❌ combine_medidok 404: {e}")
        return jsonify(success=False, message=str(e)), 404
    except ValueError as e:
        log(f"❌ combine_medidok 400: {e}")
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        log(f"❌ combine_medidok 500: {e}")
        return jsonify(success=False, message=str(e)), 500

@app.route("/commit", methods=["POST"])
def commit_changes():
    try:
        fs.commit()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

@app.route("/split_pdf", methods=["POST"])
def split_pdf_route():
    """
    Zerlegt eine PDF in einzelne Seiten.
    Unterstützt Dateien aus INPUT_ROOT oder Staging.
    """
    session_id = ensure_staging()
    data = request.get_json(force=True) or {}
    filename = data.get("file")
    
    if not filename:
        return jsonify(success=False, message="Keine Datei übergeben."), 400
    
    log(f"🔪 split_pdf gestartet für: {filename}")
    
    try:
        # Pfad auflösen: Staging ZUERST, dann INPUT_ROOT
        source_path = None
        
        # 1. Versuch: Im Staging
        staging_path = os.path.join(fs.work_dir, filename)
        if os.path.exists(staging_path):
            source_path = staging_path
            log(f"   ✓ Gefunden im Staging: {filename}")
        else:
            # 2. Versuch: Im INPUT_ROOT (Medidok)
            input_path = os.path.join(INPUT_ROOT, filename)
            if os.path.exists(input_path):
                source_path = input_path
                log(f"   ✓ Gefunden in INPUT_ROOT: {filename}")
        
        if not source_path:
            raise FileNotFoundError(f"Datei nicht gefunden: {filename}")
        
        if not filename.lower().endswith('.pdf'):
            raise ValueError("Nur PDF-Dateien können zerlegt werden")
        
        # PDF mit PyMuPDF splitten
        import fitz
        doc = fitz.open(source_path)
        
        created_files = []
        base_name = os.path.splitext(filename)[0]
        
        for page_num in range(len(doc)):
            # Neue PDF für diese Seite
            single_page = fitz.open()
            single_page.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            # Dateiname: original_seite_001.pdf
            page_filename = f"{base_name}_seite_{page_num+1:03d}.pdf"
            page_path = os.path.join(fs.work_dir, page_filename)
            
            single_page.save(page_path)
            single_page.close()
            
            created_files.append(page_filename)
            log(f"   ✓ Seite {page_num+1} erstellt: {page_filename}")
        
        doc.close()
        
        # Original-Datei als verarbeitet markieren
        if "processed_files" not in session:
            session["processed_files"] = {}
        
        session["processed_files"][filename] = {
            "operation": "split",
            "timestamp": time.time(),
            "result_count": len(created_files)
        }
        session.modified = True
        
        log(f"✅ split_pdf erfolgreich: {len(created_files)} Seiten erstellt")
        log(f"📌 Markierte Datei: {filename}")
        
        return jsonify(
            success=True,
            files=created_files,
            count=len(created_files),
            processed_file=filename
        )
        
    except FileNotFoundError as e:
        log(f"❌ split_pdf 404: {e}")
        return jsonify(success=False, message=str(e)), 404
    except ValueError as e:
        log(f"❌ split_pdf 400: {e}")
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        log(f"❌ split_pdf 500: {e}")
        import traceback
        log(traceback.format_exc(), level="error")
        return jsonify(success=False, message=str(e)), 500

@app.route("/ocr_only", methods=["POST"])
def ocr_only():
    """
    Führt nur OCR durch (ohne LLM-Analyse).
    Die Dateien werden zum Download bereitgestellt.
    """
    session_id = ensure_staging()
    payload = request.get_json(force=True) or {}
    selected = payload.get("files", [])

    # Strings oder Objekte akzeptieren
    if selected and isinstance(selected[0], dict):
        selected = [x.get("file") for x in selected if x.get("file")]

    if not selected:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400

    log(f"📄 OCR-Only gestartet für {len(selected)} Datei(en)")

    try:
        # Eingabepfade prüfen (Medidok: INPUT_ROOT, Einzel/Batch: Staging)
        file_paths = []
        for name in selected:
            # Zuerst im Staging suchen (Einzel/Batch)
            staging_path = os.path.join(fs.work_dir, name)
            if os.path.exists(staging_path):
                file_paths.append(staging_path)
                log(f"📂 Datei aus Staging: {name}")
                continue
            
            # Fallback: INPUT_ROOT (Medidok)
            abs_path = os.path.join(INPUT_ROOT, name)
            if os.path.exists(abs_path):
                file_paths.append(abs_path)
                log(f"📂 Datei aus INPUT_ROOT: {name}")
                continue
            
            # Nicht gefunden
            return jsonify(success=False, message=f"Datei nicht gefunden: {name}"), 404

        # OCR durchführen
        results = []
        for input_path in file_paths:
            filename = os.path.basename(input_path)
            base_no_ext = os.path.splitext(filename)[0]
            
            # Bilder zu PDF konvertieren
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff')):
                temp_rel = f"{base_no_ext}_converted.pdf"
                temp_pdf = os.path.join(fs.work_dir, temp_rel)
                
                with open(temp_pdf, "wb") as f:
                    f.write(img2pdf.convert([input_path]))
                
                input_path = temp_pdf
                log(f"🖼️ Bild zu PDF konvertiert: {temp_rel}")
            
            # OCR durchführen
            output_basename = f"{base_no_ext}_ocr.pdf"
            output_path = os.path.join(fs.work_dir, output_basename)
            
            try:
                result = subprocess.run(
                    ['ocrmypdf', '-l', 'deu', '--skip-text', input_path, output_path],
                    check=True, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    timeout=60
                )
                
                if os.path.exists(output_path):
                    results.append({
                        "original": filename,
                        "ocr_file": output_basename,
                        "success": True
                    })
                    log(f"✅ OCR erfolgreich: {output_basename}")
                else:
                    log(f"❌ OCR-Ausgabe nicht gefunden: {output_basename}", level="error")
                    results.append({
                        "original": filename,
                        "success": False,
                        "error": "Output file not created"
                    })
                    
            except subprocess.TimeoutExpired:
                log(f"❌ OCR Timeout bei {filename}", level="error")
                results.append({
                    "original": filename,
                    "success": False,
                    "error": "OCR Timeout (>60s)"
                })
            except subprocess.CalledProcessError as e:
                log(f"❌ OCR-Fehler bei {filename}: {e.stderr.decode()}", level="error")
                results.append({
                    "original": filename,
                    "success": False,
                    "error": e.stderr.decode()
                })
            except Exception as e:
                log(f"❌ Unerwarteter Fehler bei {filename}: {e}", level="error")
                results.append({
                    "original": filename,
                    "success": False,
                    "error": str(e)
                })

        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        log(f"✅ OCR-Only abgeschlossen: {len(successful)} erfolgreich, {len(failed)} fehlgeschlagen")

        return jsonify(
            success=True,
            results=results,
            successful=len(successful),
            failed=len(failed)
        )

    except Exception as e:
        log(f"❌ Fehler in ocr_only: {e}", level="error")
        import traceback
        log(traceback.format_exc(), level="error")
        return jsonify(success=False, message=str(e)), 500

@app.route("/list_staged_files", methods=["GET"])
def list_staged_files():
    """
    Gibt alle Dateien im aktuellen Staging zurück.
    """
    try:
        if not fs.session_id:
            return jsonify(success=True, files=[])
        
        files = []
        staging_dir = fs.work_dir
        
        if staging_dir.exists():
            for item in staging_dir.rglob('*'):
                if item.is_file():
                    # Nur Dateiname ohne Pfad zurückgeben
                    files.append(item.name)
        
        log(f"📋 Staging-Dateien aufgelistet: {len(files)} Dateien")
        return jsonify(success=True, files=sorted(files))
        
    except Exception as e:
        log(f"❌ Fehler beim Auflisten der Staging-Dateien: {e}", level="error")
        return jsonify(success=False, message=str(e)), 500

@app.route("/abort", methods=["POST"])
def abort_changes():
    try:
        sid = session.get("session_id")
        
        # Staging abräumen
        fs.abort()
        log(f"🚫 Änderungen verworfen für Session: {sid}")
        
        # Session aus Registry entfernen
        if sid:
            registry.unregister(sid)
        
        # Session clearen
        session.clear()
        
        return jsonify(success=True)
    except Exception as e:
        log(f"❌ Fehler beim Verwerfen: {e}", level="error")
        return jsonify(success=False, message=str(e)), 500

def ensure_directories():
    """Stellt sicher, dass alle benötigten Verzeichnisse existieren."""
    from config import (
        UPLOAD_FOLDER, PROCESSED_FOLDER, INPUT_ROOT, 
        WORK_ROOT, OUTPUT_ROOT, IMPORT_MEDIDOK, 
        FAIL_DIR_MEDIDOK, LOGGING_FOLDER, JSON_FOLDER,
        TRASH_DIR
    )
    
    # Lokale Verzeichnisse, die wir erstellen UND testen können
    local_dirs = [
        UPLOAD_FOLDER,
        PROCESSED_FOLDER,
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
        # Nach einem Server-Neustart sind alle Sessions ungültig
        if registry.registry_path.exists():
            registry.registry_path.unlink()
            log("🗑️ Alte Session-Registry gelöscht (Server-Neustart)")
            
            # Neue leere Registry erstellen
            registry._save({})
        
        # 3. Alle verwaisten Dateien aufräumen
        # Keine aktiven Sessions nach Neustart → set() ist leer
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
            for err in stats['errors'][:5]:  # Nur erste 5 Fehler loggen
                log(f"   - {err}", level="warning")
        
        log("✅ Startup-Cleanup abgeschlossen")
        
    except Exception as e:
        log(f"❌ Fehler beim Startup-Cleanup: {e}", level="error")
        import traceback
        log(traceback.format_exc(), level="error")

# Optionale Admin-Endpoints für manuelles Cleanup
@app.route("/admin/cleanup", methods=["POST"])
def manual_cleanup():
    """Manuelles Cleanup aller inaktiven Sessions (Admin-Funktion)."""
    try:
        # Stale Sessions finden
        stale = registry.cleanup_stale_sessions(timeout_minutes=30)
        active = registry.get_active_sessions(timeout_minutes=30)
        
        # Cleanup durchführen
        stats = cleanup_orphaned_files(
            Path(WORK_ROOT),
            Path(OUTPUT_ROOT),
            active
        )
        
        return jsonify({
            'success': True,
            'stale_sessions': len(stale),
            'active_sessions': len(active),
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route("/admin/sessions", methods=["GET"])
def list_sessions():
    """Listet alle aktiven Sessions auf."""
    from datetime import datetime
    try:
        active = registry.get_active_sessions(timeout_minutes=30)
        registry_data = registry._load()
        
        sessions = []
        for session_id in active:
            data = registry_data.get(session_id, {})
            sessions.append({
                'id': session_id,
                'started': datetime.fromtimestamp(data.get('started', 0)).isoformat(),
                'last_activity': datetime.fromtimestamp(data.get('last_activity', 0)).isoformat()
            })
        
        return jsonify({
            'success': True,
            'count': len(sessions),
            'sessions': sessions
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

if __name__ == '__main__':
    ensure_directories()
    startup_cleanup()  # ✅ Cleanup VOR dem Server-Start
    app.run(host='0.0.0.0', port=5000)