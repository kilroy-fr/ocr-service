"""
File Routes - Upload, Download, Preview
"""
import os
import time
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from urllib.parse import unquote

from services.logger import log
from services.session_manager import ensure_staging
from services.file_utils import fs
from config import INPUT_ROOT

file_bp = Blueprint('file', __name__)


@file_bp.route('/upload', methods=['POST'])
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


@file_bp.route('/upload_folder', methods=['POST'])
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


@file_bp.route('/preview/<path:filename>')
def preview_file(filename):
    """Vorschau - einfach mit UTF-8 Mount."""
    filename = unquote(filename)

    # Versuche zuerst im Staging
    if fs.session_id:
        staged = os.path.join(fs.work_dir, filename)
        if os.path.exists(staged):
            return send_from_directory(fs.work_dir, filename)

    # Fallback: Original im INPUT_ROOT
    return send_from_directory(INPUT_ROOT, filename)


@file_bp.route('/processed/<path:filename>')
def serve_processed_file(filename):
    """Liefert verarbeitete Dateien aus Staging oder Output."""
    from config import OUTPUT_ROOT

    if fs.session_id:
        staged = os.path.join(fs.work_dir, filename)
        if os.path.exists(staged):
            return send_from_directory(fs.work_dir, filename)
    return send_from_directory(OUTPUT_ROOT, filename)


@file_bp.route("/list_staged_files", methods=["GET"])
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
