from flask import Flask, request, render_template, send_from_directory, abort, Response, stream_with_context, redirect, url_for, jsonify, session
from services.logger import log_queue, log, ui_log_queue
from services.ollama_client import warmup_ollama
from services.ocr import convert_images_to_pdf_with_ocr, process_pdf, process_medidok_files, create_control_json_from_summaries
from services.file_utils import (
    fs, to_rel_under_input,
    merge_images_to_pdf, timestamped_pdf_name,
    handle_successful_processing, cleanup_old_json_files,
    clear_folder, combine_and_delete, sanitize_filename
)
from config import (
  UPLOAD_FOLDER, PROCESSED_FOLDER, DATA_FOLDER,
  INPUT_ROOT, OUTPUT_ROOT, WORK_ROOT,
  SOURCE_DIR_MEDIDOK, TARGET_DIR_MEDIDOK,  # Aliase, falls noch verwendet
  IMPORT_MEDIDOK, OLLAMA_URL, MODEL_LLM1, JSON_FOLDER
)
from weasyprint import HTML
from werkzeug.utils import secure_filename
from collections import defaultdict
from io import BytesIO

import tempfile
import uuid
import os
import queue
import time
import json
import shutil
import requests
import os as _os_patch

_os_rename_real = _os_patch.rename
_os_remove_real = _os_patch.remove

app = Flask(__name__)
app.secret_key = "REDACTED"  # Sicher & geheim aufbewahren!
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
    sid = session.get("session_id")
    if not sid:
        sid = str(uuid.uuid4())
        session["session_id"] = sid
    if not fs.session_id:
        fs.start(sid)
    log(f"Session-ID: {sid}")
    return sid
# -------------------------------------------------------------------

@app.before_request
def load_model_from_cookie():
    if "selected_model" not in session and request.cookies.get("selected_model"):
        session["selected_model"] = request.cookies.get("selected_model")
        
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
                           files=control_data,  # ✅ <-- das ist jetzt korrekt
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
        data[index]["name"] = updated["name"]
        data[index]["vorname"] = updated["vorname"]
        data[index]["geburtsdatum"] = updated["geburtsdatum"]
        data[index]["datum"] = updated["datum"]
        data[index]["beschreibung1"] = updated["beschreibung1"]
        data[index]["beschreibung2"] = updated["beschreibung2"]
        data[index]["categoryID"] = updated["categoryID"]
        data[index]["selected"] = updated["selected"]

        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        return jsonify(success=True)
    return jsonify(success=False), 400

@app.route("/finalize_import", methods=["POST"])
def finalize_import():
    payload = request.get_json(force=True) or {}
    entries = payload.get("files", [])
    if not entries:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400

    # 1) Alle geplanten Operationen committen (nimmt aus Staging -> OUTPUT_ROOT)
    try:
        fs.commit()
    except Exception as e:
        return jsonify(success=False, message=f"Commit fehlgeschlagen: {e}"), 500

    os.makedirs(IMPORT_MEDIDOK, exist_ok=True)
    moved = 0

    for entry in entries:
        rel_name = entry.get("file")          # ⚠️ MUSS der aktuelle (zuletzt gespeicherte) REL-Dateiname sein!
        include  = bool(entry.get("include"))
        if not include or not rel_name:
            continue

        src = os.path.join(OUTPUT_ROOT, rel_name)
        if not os.path.exists(src):
            # Fallback: notfalls nur Basename versuchen
            alt = os.path.join(OUTPUT_ROOT, os.path.basename(rel_name))
            if os.path.exists(alt):
                src = alt
            else:
                log(f"[WARN] finalize_import: Quelle nicht gefunden: {src}")
                continue

        dst = os.path.join(IMPORT_MEDIDOK, os.path.basename(rel_name))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        import shutil
        shutil.move(src, dst)                  # ✅ echtes Verschieben, kein os.rename
        moved += 1

    return jsonify(success=True, moved=moved)


@app.route("/rename_file", methods=["POST"])
def rename_file():
    data = request.get_json(force=True) or {}
    old_rel = data.get("old_filename")     # REL-Pfad (z. B. "Medidok/foo_ocr.pdf")
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

    # 2) Serverseitig den ZIELNAMEN nach dem Kanon-Schema bestimmen + Plan erzeugen
    #    -> wir nutzen deine zentrale Funktion (plant Rename + gibt Namen zurück)
    result = handle_successful_processing(
        summary_data=entry,                 # enthält name, vorname, geburtsdatum, datum, beschreibung1, beschreibung2, categoryID
        original_path=old_rel,             # REL ist ok; to_rel_under_input lässt REL unverändert
        target_dir=os.path.dirname(old_rel)
    )
    new_base_presan = result["renamed"]           # z.B. Nachname$Vorname$Gebdat$Dokdat$Absender, Befund$Kategorie.pdf
    new_base = sanitize_filename(new_base_presan)
    new_rel  = os.path.join(os.path.dirname(old_rel), new_base)

    # 3) Sofort im STAGING umbenennen, damit die Vorschau stimmt
    if fs.session_id:
        staged_old = os.path.join(fs.work_dir, old_rel)
        staged_new = os.path.join(fs.work_dir, new_rel)
        os.makedirs(os.path.dirname(staged_new), exist_ok=True)
        if os.path.exists(staged_old):
            os.replace(staged_old, staged_new)

    # 4) Den Eintrag in control.json auf den neuen REL-Pfad umstellen (damit finalize_import den richtigen Pfad kennt)
    for e in control_data:
        if str(e.get("file","")) == str(old_rel):
            e["file"] = new_rel
            e["filename"] = os.path.basename(new_rel)
            break
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(control_data, f, ensure_ascii=False, indent=2)

    return jsonify(success=True, new_filename=new_rel)

@app.route('/')
def index():
    session_id = ensure_staging()
    # Pfad zur individuellen JSON-Datei

    control_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")

    # Datei löschen, wenn vorhanden
    if os.path.exists(control_path):
        try:
            os.remove(control_path)
            log(f"🗑️ Session-spezifische control.json gelöscht: {control_path}")
        except Exception as e:
            log(f"⚠️ Fehler beim Löschen der Datei: {e}", level="warning")

    error_code = request.args.get("error")
    error_msg = None
    if error_code == "keine_datei":
        error_msg = "⚠️ Bitte mindestens eine Datei auswählen."

    # Subverzeichnisse laden
    subdirs = [os.path.relpath(os.path.join(dp, d), DATA_FOLDER) for dp, dn, _ in os.walk(DATA_FOLDER) for d in dn]

    # Medidok-Dateien auflisten
    medidok_files = []
    medidok_dir = INPUT_ROOT
    public_src = "/M" + INPUT_ROOT[6:] # aufhübschen für die Übergabe an index.html
    if os.path.exists(medidok_dir):
        medidok_files = [
            f for f in os.listdir(medidok_dir)
            if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png'))
        ]

    # Template einmal korrekt rendern
    return render_template(
        "index.html",
        error=error_msg,
        medidok_files=medidok_files,
        subdirs=subdirs,
        llm=session["selected_model"],
        med_src=public_src
    )

def event_stream():
    log("🔄 OCR-Service wurde gestartet.")
    yield f"data: Verbunden mit Server...\n\n"
    while True:
        try:
            message = ui_log_queue.get(timeout=1)
            yield f"data: {message}\n\n"
        except queue.Empty:
            time.sleep(0.1)

@app.route('/preview/<path:filename>')
def preview_file(filename):
    if fs.session_id:
        staged = os.path.join(fs.work_dir, filename)
        if os.path.exists(staged):
            return send_from_directory(fs.work_dir, filename)
    return send_from_directory(INPUT_ROOT, filename)

@app.route('/processed/<path:filename>')
def serve_processed_file(filename):
    if fs.session_id:
        staged = os.path.join(fs.work_dir, filename)
        if os.path.exists(staged):
            return send_from_directory(fs.work_dir, filename)
    return send_from_directory(OUTPUT_ROOT, filename)

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True)


@app.route("/stream")
def stream():
    
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/upload', methods=['POST'])
def upload_files():
    session_id = ensure_staging()
    warmup_ollama()
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        log("Keine Dateien ausgewählt")
        return 'Keine Dateien ausgewählt', 400

    image_files, pdfs = [], []
    for file in files:
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        if file.filename.lower().endswith('.pdf'):
            pdfs.append(filepath)
        elif file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff')):
            image_files.append(filepath)

    if image_files:
        merged_pdf = os.path.join(UPLOAD_FOLDER, timestamped_pdf_name())
        merge_images_to_pdf(image_files, merged_pdf)
        pdfs.append(merged_pdf)

    processed, summaries = [], []
    for pdf in pdfs:
        output_pdf, summary = process_pdf(pdf, PROCESSED_FOLDER)
        if output_pdf:
            processed.append(summary["filename"])
            summaries.append(summary)

    result_html = render_template(
        'result.html', 
        files=processed, 
        llm=session.get("selected_model", MODEL_LLM1), 
        summaries=summaries, 
        log_text=get_log_snapshot()
    )
    return result_html

@app.route('/upload_folder', methods=['POST'])
def upload_folder():
    session_id = ensure_staging()
    warmup_ollama()

    # 1. PROCESSED_FOLDER-Inhalt löschen, Ordner behalten
    if os.path.exists(PROCESSED_FOLDER):
        clear_folder(PROCESSED_FOLDER)
    else:
        os.makedirs(PROCESSED_FOLDER, exist_ok=True)

    uploaded_files = request.files.getlist("files")
    if not uploaded_files or all(f.filename == '' for f in uploaded_files):
        log("Keine Dateien empfangen")
        return 'Keine Dateien empfangen', 400

    # 🗂️ Temporäres Verzeichnis zum Zwischenspeichern der Struktur
    temp_dir = tempfile.mkdtemp()
    pdfs = []
    image_groups = defaultdict(list)

    for file in uploaded_files:
        # Pfad innerhalb des Uploads (z. B. "x/1.jpg")
        rel_path = os.path.normpath(file.filename)
        rel_path = rel_path.replace("\\", "/")  # für Windows-Klienten
        save_path = os.path.join(temp_dir, rel_path)

        # 🔐 Sicherheit: keine Pfadmanipulation
        if ".." in rel_path or rel_path.startswith("/"):
            continue

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        file.save(save_path)

        # 📁 Gruppieren
        if save_path.lower().endswith('.pdf'):
            pdfs.append(save_path)
        elif save_path.lower().endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff')):
            parent = os.path.dirname(save_path)
            image_groups[parent].append(save_path)

    # 📸 Bilder aus jedem Ordner zu einer PDF kombinieren
    for folder, image_paths in image_groups.items():
        if image_paths:
            image_paths.sort()
            base_name = os.path.basename(folder.rstrip("/\\"))
            merged_pdf_path = os.path.join(PROCESSED_FOLDER, f"{base_name}_merged.pdf")
            merge_images_to_pdf(image_paths, merged_pdf_path)
            pdfs.append(merged_pdf_path)

    # 🔍 PDFs analysieren
    processed, summaries = [], []
    for pdf in pdfs:
        output_pdf, summary = process_pdf(pdf, PROCESSED_FOLDER)
        if output_pdf:
            processed.append(summary["filename"])
            summaries.append(summary)

    # create_control_json_from_summaries(summaries)

    result_html = render_template(
        'result.html', 
        files=processed, 
        llm=session.get("selected_model", MODEL_LLM1), 
        summaries=summaries, 
        log_text=get_log_snapshot()
    )
    return result_html

@app.route('/run_medidok', methods=['POST'])
def run_medidok():
    selected_files = request.form.getlist("selected_files")
    medidok_dir = INPUT_ROOT
    medidok_target = OUTPUT_ROOT
    os.makedirs(medidok_target, exist_ok=True)
    warmup_ollama()

    if not selected_files:
        return redirect(url_for("index", error="keine_datei"))

    files_to_process = [os.path.join(medidok_dir, f) for f in selected_files]

    summaries_raw = process_medidok_files(files_to_process, medidok_target)
    
    files = [os.path.join('Medidok', s["renamed"]) for s in summaries_raw]
    summaries = [s["summary"] for s in summaries_raw]
    control_data = []
    for s in summaries_raw:
        control_data.append(s["summary"])

    return redirect(url_for("control", index=0))

@app.route("/copy_and_analyze", methods=["POST"])
def copy_and_analyze():
    log("🚀 /copy_and_analyze (Medidok) gestartet")
    session_id = ensure_staging()
    payload = request.get_json(force=True) or {}
    selected = payload.get("files", [])

    # Strings oder Objekte akzeptieren
    if selected and isinstance(selected[0], dict):
        selected = [x.get("file") for x in selected if x.get("file")]

    if not selected:
        return jsonify(success=False, message="Keine Dateien übergeben."), 400


    warmup_ollama()

    # Eingabepfade prüfen
    file_paths = []
    for name in selected:
        abs_path = os.path.join(INPUT_ROOT, name)
        if not os.path.exists(abs_path):
            return jsonify(success=False, message=f"Datei nicht gefunden: {name}"), 404
        file_paths.append(abs_path)

    try:
        # Staging-sichere Verarbeitung + Summaries erzeugen
        results = process_medidok_files(file_paths, OUTPUT_ROOT)  # fasst Originale nicht an
        summaries = [r["summary"] for r in results]
        create_control_json_from_summaries(summaries, overwrite=True, dedupe=True)

        log(f"✅ /copy_and_analyze ok – {len(summaries)} Einträge")
        return jsonify(success=True)
    except Exception as e:
        # kurzzeitig mit Text zurückgeben, damit du die nächste Stelle siehst
        log(f"❌ /copy_and_analyze Fehler: {e}", level="warning")
        return jsonify(success=False, message=str(e)), 500

@app.route("/available_models", methods=["GET"])
def available_models():
    try:
        response = requests.get(OLLAMA_URL.replace("/generate", "/tags"), timeout=5)
        response.raise_for_status()
        data = response.json()
        models = [model["name"] for model in data.get("models", [])]
        return jsonify(success=True, models=models)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

@app.route("/set_model", methods=["POST"])
def set_model():
    model = request.json.get("model")
    if not model:
        return jsonify(success=False, message="Kein Modell angegeben"), 400
    session["selected_model"] = model
    log(f"⚙️ Modell in Session gespeichert: {model}")
    return jsonify(success=True)

@app.route("/reset_session")
def reset_session():
    try:
        fs.abort()  # altes Staging wegräumen, wenn eins aktiv ist
    except Exception:
        pass
    session.clear()
    session["session_id"] = str(uuid.uuid4())
    log(f"🔁 Neue Session-ID vergeben: {session['session_id']}")
    return redirect(url_for("index"))

@app.route("/combine_medidok", methods=["POST"])
def combine_medidok_route():
    session_id = ensure_staging()
    data = request.get_json(force=True) or {}
    selected_files = data.get("files", [])
    if not selected_files:
        return jsonify(success=False, message="Keine Dateien ausgewählt."), 400

    try:
        out_name = combine_and_delete(INPUT_ROOT, selected_files)  # oder SOURCE_DIR_MEDIDOK (Alias)
        log(f"🧩 combine_medidok ok: {out_name}")
        return jsonify(success=True, combined=out_name)
    except FileNotFoundError as e:
        log(f"🧩 combine_medidok 404: {e}")
        return jsonify(success=False, message=str(e)), 404
    except ValueError as e:
        log(f"🧩 combine_medidok 400: {e}")
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        # 🪪 kurzfristig echte Fehlermeldung zurückgeben, um Ursachen zu sehen
        log(f"🧩 combine_medidok 500: {e}")
        return jsonify(success=False, message=str(e)), 500

@app.route("/commit", methods=["POST"])
def commit_changes():
    try:
        fs.commit()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

@app.route("/abort", methods=["POST"])
def abort_changes():
    try:
        fs.abort()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
        
if __name__ == '__main__':
    cleanup_old_json_files(JSON_FOLDER, days_old=1)
    app.run(host='0.0.0.0', port=5000)
