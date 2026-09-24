"""
Admin Routes - System Administration & Monitoring
"""
import requests
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify, session

from services.logger import log
from services.session_manager import registry
from services.file_utils import cleanup_orphaned_files
from config import OLLAMA_URL, MODEL_LLM1, WORK_ROOT, OUTPUT_ROOT

admin_bp = Blueprint('admin', __name__)

# Whitelist der erlaubten Modelle (kuratiert nach Qualitaetstest, siehe TESTERGEBNISSE.md).
# Frueher entfernt: qwen2.5:7b, qwen2.5:14b, gpt-oss:20b, gemma4:26b, deepseek-r1:14b.
# gemma4:26b am 24.09.2026 nachgetestet: laeuft ueber /api/chat, schreibt bei fehlenden Daten
# aber Platzhalter wie "01.01.1900" und ist nicht besser als gemma4:12b bei 18 statt 7.6 GB.
# 24.09.2026 entfernt (Test mit echten Arztbriefen in testdateien/ und T1-T9):
# - qwen3:8b, qwen3:14b: erfinden fehlende Geburts- und Briefdaten, bei jeder getesteten
#   Prompt-Variante und Temperatur (0.0-0.7). Ein erfundenes Geburtsdatum ordnet den Brief
#   in Medidok dem falschen Patienten zu - auch wenn die OCR das Datum nur nicht lesen konnte.
# - gemma4:e2b: vertauscht Vor-/Nachname und Empfaenger/Absender, laesst Zeilen aus, sodass
#   alle folgenden Felder verrutschen.
ALLOWED_MODELS = [
    "gemma4:12b",   #  7.6 GB - echte Briefe 100%, T1-T9 97%, laesst fehlende Daten leer
]

# Kurzbeschreibung je Modell fuers Frontend-Dropdown (siehe TESTERGEBNISSE.md)
MODEL_DESCRIPTIONS = {
    "gemma4:12b":  "Empfohlen - zuverlaessig, erfindet keine Daten",
}


@admin_bp.route("/available_models", methods=["GET"])
def available_models():
    """Gibt Liste verfügbarer LLM-Modelle zurück."""
    try:
        response = requests.get(OLLAMA_URL.replace("/generate", "/tags"), timeout=5)
        response.raise_for_status()
        data = response.json()
        all_models = [model["name"] for model in data.get("models", [])]

        # Nur erlaubte Modelle filtern
        models = [m for m in all_models if m in ALLOWED_MODELS]

        # Falls keine erlaubten Modelle gefunden, Fallback
        if not models:
            models = [MODEL_LLM1]

        # Aktuell ausgewähltes Modell mitgeben
        current = session.get("selected_model")
        descriptions = {m: MODEL_DESCRIPTIONS[m] for m in models if m in MODEL_DESCRIPTIONS}

        return jsonify(
            success=True,
            models=models,
            current=current,
            descriptions=descriptions
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


@admin_bp.route("/set_model", methods=["POST"])
def set_model():
    """Setzt das aktuell verwendete LLM-Modell."""
    model = request.json.get("model")
    if not model:
        return jsonify(success=False, message="Kein Modell angegeben"), 400
    if model not in ALLOWED_MODELS:
        return jsonify(success=False, message=f"Modell nicht freigegeben: {model}"), 400

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


@admin_bp.route("/admin/cleanup", methods=["POST"])
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


@admin_bp.route("/admin/sessions", methods=["GET"])
def list_sessions():
    """Listet alle aktiven Sessions auf."""
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
