import os
import re
import shutil
import subprocess
import img2pdf
import json
from .summarizer import summarize_pdf
from .file_utils import fs, to_rel_under_input, safe_line, handle_successful_processing
from .logger import log
from config import PROCESSED_FOLDER, SOURCE_DIR_MEDIDOK, FAIL_DIR_MEDIDOK, JSON_FOLDER
from flask import render_template, session

def process_pdf(pdf_path, output_dir_unused):
    """
    OCR eines einzelnen PDFs:
    - schreibt NUR ins Staging (virtueller Zielpfad = <rel_dir>/<basename>_ocr.pdf)
    - erzeugt Summary
    - KEINE Mutation an Originalen
    """
    # Basis: relativer Pfad unter INPUT_ROOT bestimmen (für den virtuellen Output)
    rel_src = to_rel_under_input(pdf_path)  # wenn pdf_path im Input liegt
    if not rel_src:
        # Fallback: pdf_path liegt evtl. schon im Staging (z.B. aus Image-Conversion)
        # dann orientieren wir uns am Original-Dateinamen
        base = os.path.basename(pdf_path)
        rel_src = base  # landet flach unter work/session/staging/<base>_ocr.pdf

    rel_dir = os.path.dirname(rel_src)
    base_no_ext = os.path.splitext(os.path.basename(rel_src))[0]
    out_rel = os.path.join(rel_dir, f"{base_no_ext}_ocr.pdf")

    staged_out = ocr_to_staging(pdf_path, out_rel)
    if not staged_out:
        return None, None

    # Summary für die Vorschau (Datei ist im Staging, aber wir merken uns den REL-Pfad)
    summary = summarize_pdf(staged_out)
    text = (summary or "").strip()
    lines = [(s or "").strip() for s in text.split("\n")]

    summary_data = {
        "file": out_rel,  # WICHTIG: relativer "virtueller" Pfad für control.html
        "filename": os.path.basename(staged_out),
        "name": safe_line(lines, 0, "Unbekannt"),
        "vorname": safe_line(lines, 1, "Unbekannt"),
        "geburtsdatum": safe_line(lines, 2, "Unbekannt"),
        "datum": safe_line(lines, 3, "Unbekannt"),
        "beschreibung1": safe_line(lines, 4, "Kein Arzt erkannt"),
        "beschreibung2": safe_line(lines, 5, "Keine Beschreibung verfügbar"),
        "categoryID": safe_line(lines, 6, "11"),
    }

    create_control_json_from_summaries([summary_data])
    handle_successful_processing(
        summary_data=summary_data,
        original_path=staged_out,  # die Staging-Datei
        target_dir=os.path.dirname(staged_out)
    )    
    return staged_out, summary_data


def convert_images_to_pdf_with_ocr(input_dir, output_dir_unused):
    """
    Konvertiert JPG/PNG in ein temporäres PDF im STAGING und führt dann OCR aus.
    - KEINE Original-Deletes mehr
    - Rückgabe: Liste staging-Pfade + Summaries
    """
    processed_files, summaries = [], []

    for root, _, files in os.walk(input_dir):
        images = sorted([os.path.join(root, f) for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        pdfs = sorted([os.path.join(root, f) for f in files if f.lower().endswith('.pdf')])

        temp_pdf_path = None
        rel_dir = to_rel_under_input(root)  # für Output-Relpfade
        if images:
            # temporäres PDF im STAGING bauen (nicht im Input!)
            temp_name = os.path.basename(root) + ".pdf"
            temp_rel  = os.path.join(rel_dir if rel_dir else "", temp_name)
            temp_pdf_path = os.path.join(fs.work_dir, temp_rel)
            os.makedirs(os.path.dirname(temp_pdf_path), exist_ok=True)
            with open(temp_pdf_path, "wb") as f:
                f.write(img2pdf.convert(images))
            pdfs.append(temp_pdf_path)  # wir OCR'n dieses staging-PDF

        for pdf in pdfs:
            # Output-Relpfad ableiten
            if pdf.startswith(fs.work_dir):
                # staging-Temp: orientiere dich an rel_dir
                base_no_ext = os.path.splitext(os.path.basename(pdf))[0]
                out_rel = os.path.join(rel_dir if rel_dir else "", f"{base_no_ext}_ocr.pdf")
            else:
                src_rel = to_rel_under_input(pdf)
                d = os.path.dirname(src_rel) if src_rel else ""
                base_no_ext = os.path.splitext(os.path.basename(pdf))[0]
                out_rel = os.path.join(d, f"{base_no_ext}_ocr.pdf")

            staged_out = ocr_to_staging(pdf, out_rel)
            if staged_out:
                processed_files.append(staged_out)
                # Summary erzeugen
                summary = summarize_pdf(staged_out)
                text = (summary or "").strip()
                lines = [(s or "").strip() for s in text.split("\n")]
                summaries.append({
                    "file": out_rel,
                    "filename": os.path.basename(staged_out),
                    "name": safe_line(lines, 0, "Unbekannt"),
                    "vorname": safe_line(lines, 1, "Unbekannt"),
                    "geburtsdatum": safe_line(lines, 2, "Unbekannt"),
                    "datum": safe_line(lines, 3, "Unbekannt"),
                    "beschreibung1": safe_line(lines, 4, "Kein Arzt erkannt"),
                    "beschreibung2": safe_line(lines, 5, "Keine Beschreibung verfügbar"),
                    "categoryID": safe_line(lines, 6, "11"),
                })

    return processed_files, summaries

def process_medidok_files(file_paths, target_dir_unused):
    """
    Verarbeitet Medidok-Dateien staging-sicher:
    - Bilddateien -> temp PDF im Staging -> OCR im Staging
    - KEIN Verschieben nach FAIL_DIR, KEIN Löschen der Originale
    - Rückgabe: Liste Ergebnis-Metadaten für UI
    """
    results = []

    for original_file_path in file_paths:
        filename = os.path.basename(original_file_path)
        if not filename.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
            continue

        original_file_path = os.path.join(SOURCE_DIR_MEDIDOK, filename)
        working_input = original_file_path

        # Falls Bild: erst staging-Temp-PDF erzeugen
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            rel_dir = to_rel_under_input(SOURCE_DIR_MEDIDOK) or ""
            temp_rel = os.path.join(rel_dir, os.path.splitext(filename)[0] + "_converted.pdf")
            temp_pdf = os.path.join(fs.work_dir, temp_rel)
            os.makedirs(os.path.dirname(temp_pdf), exist_ok=True)
            with open(temp_pdf, "wb") as f:
                f.write(img2pdf.convert([original_file_path]))
            working_input = temp_pdf

        # OCR im Staging
        src_rel = to_rel_under_input(original_file_path) or ""
        base_no_ext = os.path.splitext(os.path.basename(original_file_path))[0]
        out_rel = os.path.join(os.path.dirname(src_rel), f"{base_no_ext}_ocr.pdf")
        staged_out = ocr_to_staging(working_input, out_rel)

        if not staged_out:
            log(f"❌ Fehler bei Verarbeitung – Original bleibt unverändert: {original_file_path}")
            continue

        # Summary + Umbenennungsplan (handle_successful_processing plant nur!)
        summary = summarize_pdf(staged_out)
        text = (summary or "").strip()
        lines = [(s or "").strip() for s in text.split("\n")]
        summary_data = {
            "file": out_rel,
            "filename": os.path.basename(staged_out),
            "name": safe_line(lines, 0, "Unbekannt"),
            "vorname": safe_line(lines, 1, "Unbekannt"),
            "geburtsdatum": safe_line(lines, 2, "Unbekannt"),
            "datum": safe_line(lines, 3, "Unbekannt"),
            "beschreibung1": safe_line(lines, 4, "Kein Arzt erkannt"),
            "beschreibung2": safe_line(lines, 5, "Keine Beschreibung verfügbar"),
            "categoryID": safe_line(lines, 6, "11"),
        }
        create_control_json_from_summaries([summary_data])

        result = handle_successful_processing(
            summary_data=summary_data,
            original_path=staged_out,  # hier: die STAGING-Datei
            target_dir=os.path.dirname(staged_out)
        )
        results.append(result)

    return results

def create_control_json_from_summaries(summaries, *, overwrite=False, dedupe=True, key="file"):
    """Schreibt/aktualisiert control_<session>.json.
    - overwrite=True: bestehende Datei wird ersetzt
    - dedupe=True: doppelte Einträge (gleicher key) werden überschrieben
    """
    sid = session.get("session_id", "default")
    path = os.path.join(JSON_FOLDER, f"control_{sid}.json")
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

def ocr_to_staging(input_pdf_path: str, output_rel: str):
    """
    Führt OCR aus und schreibt die Ausgabe NUR ins Staging unter output_rel.
    - input_pdf_path: kann im Input oder im Staging liegen
    - output_rel: relativer Pfad unter INPUT_ROOT, wo die Datei VIRTUELL liegen würde
    """
    # absoluter Staging-Zielpfad
    staged_out = os.path.join(fs.work_dir, output_rel)
    os.makedirs(os.path.dirname(staged_out), exist_ok=True)

    try:
        result = subprocess.run(
            ['ocrmypdf', '-l', 'deu', '--skip-text', input_pdf_path, staged_out],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as e:
        log(f"❌ OCR-Fehler bei {input_pdf_path}: {e.stderr.decode()}")
        return None

    if not os.path.exists(staged_out):
        log(f"❌ OCR-Zieldatei fehlt: {staged_out}")
        return None

    return staged_out