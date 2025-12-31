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
            from PIL import Image
            filename = file.filename

            # ✅ Dateien ohne gültige Dateiendung als .jpg behandeln
            # Prüfe ob Datei eine bekannte Endung hat
            has_valid_extension = filename.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'))
            if not has_valid_extension:
                log(f"📝 Datei ohne gültige Endung erkannt beim Upload: {filename}")
                filename = filename + '.jpg'
                log(f"✅ Dateiname ergänzt: {filename}")

            # Sichere den Dateinamen
            safe_name = secure_filename(filename)

            # ✅ TIF/TIFF direkt zu JPG konvertieren (ohne TIF zu speichern)
            if safe_name.lower().endswith(('.tif', '.tiff')):
                try:
                    log(f"🔄 TIF/TIFF wird zu JPG konvertiert: {safe_name}")

                    # TIF direkt aus Upload-Stream öffnen
                    img = Image.open(file.stream)

                    # Erste Seite bei Multi-Page TIFF
                    if hasattr(img, 'n_frames') and img.n_frames > 1:
                        img.seek(0)

                    # RGB konvertieren für JPG
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')

                    # Neuer JPG-Dateiname
                    base_name = os.path.splitext(safe_name)[0]
                    jpg_name = base_name + '.jpg'
                    jpg_path = os.path.join(fs.work_dir, jpg_name)

                    # Als JPG speichern
                    img.save(jpg_path, 'JPEG', quality=95)
                    img.close()

                    log(f"✅ TIF zu JPG konvertiert (TIF nicht gespeichert): {jpg_name}")
                    uploaded_files.append(jpg_name)
                except Exception as e:
                    log(f"❌ Fehler bei TIF-Konvertierung: {e}", level="error")
                    # Bei Fehler: TIF-Original speichern
                    staging_path = os.path.join(fs.work_dir, safe_name)
                    file.seek(0)  # Stream zurückspulen
                    file.save(staging_path)
                    uploaded_files.append(safe_name)
            else:
                # Normale Dateien (PDF, JPG, PNG) direkt speichern
                staging_path = os.path.join(fs.work_dir, safe_name)
                file.save(staging_path)
                uploaded_files.append(safe_name)

            log(f"📤 Datei ins Staging kopiert: {uploaded_files[-1]}")

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

        from PIL import Image

        # Nur Dateiname, keine Pfadstruktur
        filename = os.path.basename(file.filename)

        # ✅ Dateien ohne gültige Dateiendung als .jpg behandeln
        # Prüfe ob Datei eine bekannte Endung hat
        has_valid_extension = filename.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'))
        if not has_valid_extension:
            log(f"📝 Datei ohne gültige Endung erkannt beim Upload: {filename}")
            filename = filename + '.jpg'
            log(f"✅ Dateiname ergänzt: {filename}")

        # Nur unterstützte Formate
        if not filename.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff')):
            log(f"⏭️ Überspringe Datei (nicht unterstützt): {filename}")
            continue

        # Sichere den Dateinamen
        safe_name = secure_filename(filename)

        # ✅ TIF/TIFF direkt zu JPG konvertieren (ohne TIF zu speichern)
        if safe_name.lower().endswith(('.tif', '.tiff')):
            try:
                log(f"🔄 TIF/TIFF wird zu JPG konvertiert: {safe_name}")

                # TIF direkt aus Upload-Stream öffnen
                img = Image.open(file.stream)

                # Erste Seite bei Multi-Page TIFF
                if hasattr(img, 'n_frames') and img.n_frames > 1:
                    img.seek(0)

                # RGB konvertieren für JPG
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                # Neuer JPG-Dateiname
                base_name = os.path.splitext(safe_name)[0]
                jpg_name = base_name + '.jpg'
                jpg_path = os.path.join(fs.work_dir, jpg_name)

                # Bei Namenskonflikten: Timestamp hinzufügen
                if os.path.exists(jpg_path):
                    jpg_name = f"{base_name}_{int(time.time())}.jpg"
                    jpg_path = os.path.join(fs.work_dir, jpg_name)

                # Als JPG speichern
                img.save(jpg_path, 'JPEG', quality=95)
                img.close()

                log(f"✅ TIF zu JPG konvertiert (TIF nicht gespeichert): {jpg_name}")
                collected_files.append(jpg_name)
            except Exception as e:
                log(f"❌ Fehler bei TIF-Konvertierung: {e}", level="error")
                # Bei Fehler: TIF-Original speichern
                staging_path = os.path.join(fs.work_dir, safe_name)
                if os.path.exists(staging_path):
                    base, ext = os.path.splitext(safe_name)
                    safe_name = f"{base}_{int(time.time())}{ext}"
                    staging_path = os.path.join(fs.work_dir, safe_name)
                file.seek(0)  # Stream zurückspulen
                file.save(staging_path)
                collected_files.append(safe_name)
        else:
            # Normale Dateien (PDF, JPG, PNG) direkt speichern
            staging_path = os.path.join(fs.work_dir, safe_name)

            # Bei Namenskonflikten: Präfix mit Timestamp
            if os.path.exists(staging_path):
                base, ext = os.path.splitext(safe_name)
                safe_name = f"{base}_{int(time.time())}{ext}"
                staging_path = os.path.join(fs.work_dir, safe_name)

            file.save(staging_path)
            collected_files.append(safe_name)

        log(f"📤 Datei ins Staging kopiert: {collected_files[-1]}")

    if not collected_files:
        return jsonify(success=False, message="Keine verarbeitbaren Dateien gefunden"), 400

    log(f"📁 Batch-Upload: {len(collected_files)} Datei(en) ins Staging kopiert (ohne OCR)")
    return jsonify(success=True, files=collected_files, count=len(collected_files))


@file_bp.route('/preview/<path:filename>')
def preview_file(filename):
    """Vorschau - TIF-Dateien wurden bereits beim Upload zu JPG konvertiert."""
    filename = unquote(filename)

    # Pfad zur Datei finden
    if fs.session_id:
        staged = os.path.join(fs.work_dir, filename)
        if os.path.exists(staged):
            return send_from_directory(fs.work_dir, filename)

    # Fallback: Original im INPUT_ROOT
    original = os.path.join(INPUT_ROOT, filename)
    if os.path.exists(original):
        return send_from_directory(INPUT_ROOT, filename)

    return jsonify(success=False, message="Datei nicht gefunden"), 404


@file_bp.route('/processed/<path:filename>')
def serve_processed_file(filename):
    """Liefert verarbeitete Dateien aus Staging oder Output."""
    from config import OUTPUT_ROOT

    filename = unquote(filename)

    if fs.session_id:
        staged = os.path.join(fs.work_dir, filename)
        if os.path.exists(staged):
            return send_from_directory(fs.work_dir, filename)

    output = os.path.join(OUTPUT_ROOT, filename)
    if os.path.exists(output):
        return send_from_directory(OUTPUT_ROOT, filename)

    return jsonify(success=False, message="Datei nicht gefunden"), 404


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
