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
    IMPORT_MEDIDOK, TRASH_DIR, MODEL_LLM1, HOME_URL
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
                           index=index,
                           home_url=HOME_URL)


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
    """Benennt Datei nach Kanon-Schema um (nur in control.json, echte Umbenennung erfolgt beim Commit)."""
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

    # Zielnamen nach Kanon-Schema bestimmen (OHNE fs.plan_rename aufzurufen!)
    feld1 = sanitize_filename(entry.get("name", "Unbekannt"))
    feld2 = sanitize_filename(entry.get("vorname", "Unbekannt"))
    feld3 = sanitize_filename(entry.get("geburtsdatum", "Unbekannt"))
    feld4 = sanitize_filename(entry.get("datum", "Unbekannt"))
    feld5 = sanitize_filename(entry.get("beschreibung1", "Unbekannt"))[:30]
    feld6 = sanitize_filename(entry.get("beschreibung2", "Unbekannt"))[:120]
    feld7 = sanitize_filename(entry.get("categoryID", "11"))

    new_base = f"{feld1}_{feld2}_{feld3}_{feld4}_{feld5}, {feld6}_{feld7}.pdf"
    # WICHTIG: sanitize_filename NICHT auf new_base anwenden, da die Unterstriche Trennzeichen sind!
    new_rel = os.path.join(os.path.dirname(old_rel), new_base) if "/" in old_rel else new_base

    # Eintrag in control.json aktualisieren
    for e in control_data:
        if str(e.get("file", "")) == str(old_rel):
            e["file"] = new_rel
            e["filename"] = os.path.basename(new_rel)
            break

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(control_data, f, ensure_ascii=False, indent=2)

    log(f"📝 Dateiname in control.json aktualisiert: {old_rel} → {new_rel} (physische Umbenennung erfolgt beim Commit)")

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

    # 0) VOR dem Commit: Umbenennungen aus control.json planen
    # Problem: In control.json steht bereits der neue Dateiname, aber die physische Datei
    # im Staging hat noch den ursprünglichen Namen (*_ocr.pdf aus der Analyse).
    # Lösung: Finde die tatsächliche Datei im Staging und plane die Umbenennung.

    json_path = os.path.join(JSON_FOLDER, f"control_{sid}.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            control_data = json.load(f)

        # fs.work_dir ist bereits das Staging-Verzeichnis (.../session_id/staging)
        staging_dir = str(fs.work_dir) if hasattr(fs, 'work_dir') else None

        if staging_dir and os.path.exists(staging_dir):
            # Liste alle Dateien im Staging
            staging_files = {}
            for fname in os.listdir(staging_dir):
                if fname.endswith(".pdf"):
                    # Speichere ohne Pfad für einfachen Vergleich
                    staging_files[fname] = fname

            log(f"📂 Gefundene Dateien im Staging ({staging_dir}): {list(staging_files.keys())}")

            for entry in control_data:
                new_rel_name = entry.get("file")  # Neuer relativer Pfad aus control.json
                original_fname = entry.get("originalFilename", "")  # Original-Dateiname

                # Der ursprüngliche Name der OCR-Datei ist original_fname + "_ocr.pdf"
                # Bei TXT-Dateien ist es "_txt_converted.pdf"
                if original_fname:
                    base = os.path.splitext(original_fname)[0]

                    # Prüfe ob es eine TXT-Datei war
                    if original_fname.lower().endswith('.txt'):
                        old_fname = f"{base}_txt_converted.pdf"
                    else:
                        old_fname = f"{base}_ocr.pdf"

                    if old_fname in staging_files:
                        # Plane Umbenennung: alter Name → neuer Name (nur Basisname)
                        new_fname = os.path.basename(new_rel_name)

                        if old_fname != new_fname:
                            fs.plan_rename(old_fname, new_fname)
                            log(f"🔄 Plane Umbenennung: {old_fname} → {new_fname}")
                        else:
                            log(f"ℹ️ Keine Umbenennung nötig: {old_fname}")
                    else:
                        log(f"⚠️ Datei nicht im Staging gefunden: {old_fname}")
        else:
            log(f"⚠️ Staging-Verzeichnis nicht gefunden: {staging_dir}")

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
    """Kombiniert mehrere PDFs und/oder Bilder (JPG, PNG, TIF) zu einer PDF-Datei."""
    session_id = ensure_staging()
    data = request.get_json(force=True) or {}
    selected_files = data.get("files", [])

    if not selected_files:
        return jsonify(success=False, message="Keine Dateien ausgewählt."), 400

    log(f"🧩 combine_medidok gestartet mit {len(selected_files)} Dateien")

    try:
        from PIL import Image
        import tempfile

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

        # Temporäre PDFs für Bildkonvertierung
        temp_pdfs = []

        # Kombinieren mit PyMuPDF
        combined_pdf = fitz.open()

        for path in resolved_paths:
            file_ext = os.path.splitext(path)[1].lower()

            # Unterscheide zwischen PDF und Bilddateien
            if file_ext == '.pdf':
                # PDF direkt einfügen
                with fitz.open(path) as pdf:
                    combined_pdf.insert_pdf(pdf)
                log(f"✅ PDF hinzugefügt: {os.path.basename(path)}")
            elif file_ext in ['.jpg', '.jpeg', '.png', '.tif', '.tiff']:
                # Bild zu PDF konvertieren und einfügen
                try:
                    img = Image.open(path)

                    # Multi-Page TIFF: Alle Seiten verarbeiten
                    if file_ext in ['.tif', '.tiff'] and hasattr(img, 'n_frames') and img.n_frames > 1:
                        for frame_idx in range(img.n_frames):
                            img.seek(frame_idx)
                            frame = img.convert('RGB')

                            # Temporäres PDF für diese Seite
                            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                                temp_pdf_path = tmp.name
                                temp_pdfs.append(temp_pdf_path)
                                frame.save(temp_pdf_path, 'PDF', resolution=100.0)

                            # Ins kombinierte PDF einfügen
                            with fitz.open(temp_pdf_path) as pdf:
                                combined_pdf.insert_pdf(pdf)

                        log(f"✅ Multi-Page TIFF hinzugefügt ({img.n_frames} Seiten): {os.path.basename(path)}")
                    else:
                        # Einzelbild zu RGB konvertieren
                        if img.mode not in ('RGB', 'L'):
                            img = img.convert('RGB')

                        # Temporäres PDF erstellen
                        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                            temp_pdf_path = tmp.name
                            temp_pdfs.append(temp_pdf_path)
                            img.save(temp_pdf_path, 'PDF', resolution=100.0)

                        # Ins kombinierte PDF einfügen
                        with fitz.open(temp_pdf_path) as pdf:
                            combined_pdf.insert_pdf(pdf)

                        log(f"✅ Bild zu PDF konvertiert und hinzugefügt: {os.path.basename(path)}")

                    img.close()
                except Exception as img_error:
                    log(f"❌ Fehler beim Konvertieren von {os.path.basename(path)}: {img_error}", level="error")
                    raise
            else:
                log(f"⚠️ Nicht unterstütztes Dateiformat übersprungen: {os.path.basename(path)}", level="warning")

        # Ausgabedateiname
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"combined_{timestamp}.pdf"
        out_path = os.path.join(fs.work_dir, out_name)

        combined_pdf.save(out_path)
        combined_pdf.close()

        # Temporäre PDFs aufräumen
        for temp_pdf in temp_pdfs:
            try:
                os.unlink(temp_pdf)
            except Exception:
                pass

        log(f"✅ PDF kombiniert: {out_name} ({len(resolved_paths)} Dateien)")

        # Als verarbeitet markieren - WICHTIG: Ursprungsdateien werden ausgegraut
        if "processed_files" not in session:
            session["processed_files"] = {}

        for file in selected_files:
            session["processed_files"][file] = {
                "operation": "merged",
                "timestamp": time.time(),
                "result": out_name
            }
        session.modified = True

        log(f"🔒 {len(selected_files)} Quelldateien als 'merged' markiert (werden von Analyse ausgeschlossen)")

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


@control_bp.route("/rotate_pdf", methods=["POST"])
def rotate_pdf():
    """Rotiert eine PDF-Datei um 90°, 180° oder -90° und analysiert sie neu."""
    try:
        data = request.get_json(force=True) or {}
        filename = data.get("filename")
        direction = data.get("direction", "right")  # "right" = 90°, "left" = -90°, "180" = 180°

        if not filename:
            return jsonify(success=False, message="Kein Dateiname angegeben"), 400

        # Datei im Staging finden
        file_path = os.path.join(fs.work_dir, filename)

        if not os.path.exists(file_path):
            log(f"❌ Datei nicht gefunden: {file_path}", level="error")
            return jsonify(success=False, message="Datei nicht gefunden"), 404

        # Prüfe ob es eine PDF ist
        if not filename.lower().endswith('.pdf'):
            return jsonify(success=False, message="Nur PDF-Dateien können gedreht werden"), 400

        # Rotation bestimmen
        if direction == "180":
            angle = 180
        elif direction == "right":
            angle = 90
        else:  # left
            angle = -90

        # PDF öffnen und rotieren
        doc = fitz.open(file_path)
        for page in doc:
            page.set_rotation((page.rotation + angle) % 360)

        # Temporäre Datei für Ausgabe
        temp_path = file_path + ".tmp"
        doc.save(temp_path)
        doc.close()

        # Original ersetzen
        os.replace(temp_path, file_path)

        log(f"✅ PDF gedreht ({angle}°): {filename}")

        # Neu-Analyse durchführen
        log(f"🔄 Starte Neu-Analyse nach Rotation: {filename}")

        from services.summarizer import summarize_pdf

        try:
            # Analysiere gedrehtes PDF neu mit summarize_pdf
            summary_result = summarize_pdf(file_path, MODEL_LLM1)

            if not summary_result or summary_result.startswith("Fehler") or summary_result.startswith("Unbekannt"):
                log(f"⚠️ Keine verwertbaren Analysedaten nach Rotation", level="warning")
                return jsonify(
                    success=True,
                    message=f"PDF um {angle}° gedreht (keine Analysedaten)",
                    filename=filename,
                    reanalyzed=False
                )

            # Parse 7-Zeilen-Format von summarize_pdf
            lines = summary_result.split("\n")
            if len(lines) < 7:
                log(f"⚠️ Unvollständige Analysedaten", level="warning")
                return jsonify(
                    success=True,
                    message=f"PDF um {angle}° gedreht (unvollständige Daten)",
                    filename=filename,
                    reanalyzed=False
                )

            # Erstelle fields-Dictionary aus den 7 Zeilen
            fields = {
                "name": (lines[0] or "").strip(),
                "vorname": (lines[1] or "").strip(),
                "geburtsdatum": (lines[2] or "").strip(),
                "datum": (lines[3] or "").strip(),
                "beschreibung1": (lines[4] or "").strip(),
                "beschreibung2": (lines[5] or "").strip()
            }

            # Control-JSON aktualisieren
            session_id = session.get("session_id", "default")
            json_path = os.path.join(JSON_FOLDER, f"control_{session_id}.json")

            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    control_data = json.load(f)

                # Finde den richtigen Eintrag und aktualisiere die Felder
                for i, entry in enumerate(control_data):
                    if entry.get("filename") == filename or entry.get("file") == filename:
                        # Aktualisiere nur die erkannten Felder, behalte den Rest
                        entry.update({
                            "name": fields.get("name", entry.get("name", "")),
                            "vorname": fields.get("vorname", entry.get("vorname", "")),
                            "geburtsdatum": fields.get("geburtsdatum", entry.get("geburtsdatum", "")),
                            "datum": fields.get("datum", entry.get("datum", "")),
                            "beschreibung1": fields.get("beschreibung1", entry.get("beschreibung1", "")),
                            "beschreibung2": fields.get("beschreibung2", entry.get("beschreibung2", ""))
                        })
                        log(f"✅ Control-JSON aktualisiert für Index {i}")
                        break

                # JSON speichern
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(control_data, f, ensure_ascii=False, indent=2)

                log(f"✅ Neu-Analyse abgeschlossen: {filename}")
                return jsonify(
                    success=True,
                    message=f"PDF um {angle}° gedreht und neu analysiert",
                    filename=filename,
                    reanalyzed=True,
                    fields=fields
                )
            else:
                log(f"⚠️ Control-JSON nicht gefunden: {json_path}", level="warning")
                return jsonify(
                    success=True,
                    message=f"PDF um {angle}° gedreht (Metadaten nicht gefunden)",
                    filename=filename,
                    reanalyzed=False
                )

        except Exception as e:
            log(f"⚠️ Fehler bei Neu-Analyse: {e}", level="warning")
            # Rotation war erfolgreich, auch wenn Analyse fehlschlug
            return jsonify(
                success=True,
                message=f"PDF um {angle}° gedreht (Analyse fehlgeschlagen)",
                filename=filename,
                reanalyzed=False,
                error=str(e)
            )

    except Exception as e:
        log(f"❌ rotate_pdf: {e}", level="error")
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
