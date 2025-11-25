"""
Background Tasks Module
Handles asynchronous analysis operations
"""
import os
import json
import threading
from typing import List, Dict
from services.logger import log
from services.ocr import process_medidok_files_with_model
from config import JSON_FOLDER, OUTPUT_ROOT

# Globaler Status-Tracker für progressive Analysen
analysis_status: Dict[str, dict] = {}
analysis_lock = threading.Lock()


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

            # Thread-sichere Analyse MIT explizitem Modell
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
        index = {str(entry.get(key, "")): i for i, entry in enumerate(control_data)}
    else:
        index = {}

    # Neue Einträge einpflegen
    for s in summaries:
        entry = {
            "file": s.get("file", ""),
            "filename": s.get("filename", ""),
            "originalFilename": s.get("originalFilename", s.get("filename", "")),
            "name": s.get("name", ""),
            "vorname": s.get("vorname", ""),
            "geburtsdatum": s.get("geburtsdatum", ""),
            "datum": s.get("datum", ""),
            "beschreibung1": s.get("beschreibung1", ""),
            "beschreibung2": s.get("beschreibung2", ""),
            "categoryID": s.get("categoryID", ""),
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


def get_analysis_status(session_id: str) -> dict:
    """
    Gibt den aktuellen Analyse-Status für eine Session zurück.

    Args:
        session_id: Flask Session-ID

    Returns:
        dict: Status-Dictionary oder None
    """
    with analysis_lock:
        return analysis_status.get(session_id)
