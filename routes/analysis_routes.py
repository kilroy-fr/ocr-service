"""
Analysis Routes - OCR and LLM Analysis
"""
import os
import threading
import subprocess
import img2pdf
from flask import Blueprint, request, jsonify, session

from services.logger import log
from services.session_manager import ensure_staging
from services.ollama_client import warmup_ollama
from services.ocr import process_medidok_files, create_control_json_from_summaries
from services.background_tasks import (
    background_analyze_files,
    get_analysis_status,
    create_control_json_from_summaries_explicit
)
from services.file_utils import fs
from config import INPUT_ROOT, OUTPUT_ROOT, MODEL_LLM1

analysis_bp = Blueprint('analysis', __name__)


@analysis_bp.route("/copy_and_analyze", methods=["POST"])
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

    # Modell aus Session holen (jetzt, solange wir im Request-Context sind)
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
        # ERSTE DATEI SOFORT ANALYSIEREN
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

        # RESTLICHE DATEIEN IM HINTERGRUND
        if len(file_paths) > 1:
            log(f"🔄 Starte Background-Analyse für {len(file_paths) - 1} weitere Dateien")

            # Session-ID UND Modell explizit übergeben für Background-Thread
            thread = threading.Thread(
                target=background_analyze_files,
                args=(session_id, file_paths, current_model, 1),
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


@analysis_bp.route("/analysis_status", methods=["GET"])
def analysis_status():
    """
    Gibt den aktuellen Analyse-Status für die Session zurück.
    """
    session_id = session.get("session_id")

    if not session_id:
        return jsonify(success=False, message="Keine Session gefunden"), 400

    status = get_analysis_status(session_id)

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


@analysis_bp.route("/ocr_only", methods=["POST"])
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
                # ✅ Dateien ohne gültige Dateiendung als .jpg behandeln und umbenennen
                has_valid_extension = name.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'))
                if not has_valid_extension:
                    log(f"📝 Datei ohne gültige Endung erkannt: {name}")
                    new_name = name + '.jpg'
                    new_staging_path = os.path.join(fs.work_dir, new_name)
                    import shutil
                    shutil.move(staging_path, new_staging_path)
                    staging_path = new_staging_path
                    log(f"✅ Im Staging umbenannt: {new_name}")

                file_paths.append(staging_path)
                log(f"📂 Datei aus Staging: {os.path.basename(staging_path)}")
                continue

            # Fallback: INPUT_ROOT (Medidok)
            abs_path = os.path.join(INPUT_ROOT, name)
            if os.path.exists(abs_path):
                # ✅ Dateien ohne gültige Dateiendung als .jpg behandeln und umbenennen
                has_valid_extension = name.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'))
                if not has_valid_extension:
                    log(f"📝 Datei ohne gültige Endung erkannt: {name}")
                    new_name = name + '.jpg'
                    new_abs_path = os.path.join(INPUT_ROOT, new_name)
                    import shutil
                    shutil.move(abs_path, new_abs_path)
                    abs_path = new_abs_path
                    log(f"✅ In INPUT_ROOT umbenannt: {new_name}")

                file_paths.append(abs_path)
                log(f"📂 Datei aus INPUT_ROOT: {os.path.basename(abs_path)}")
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
