import os
import re
import fitz
from flask import session
from config import PROMPT_TEMPLATE, INPUT_ROOT, MODEL_LLM1
from .ollama_client import send_to_ollama
from .logger import log
from .file_utils import sanitize_filename, fs

def _resolve_path_for_read(pdf_path: str) -> str | None:
    """
    Nimmt REL- oder ABS-Pfad entgegen und liefert einen lesbaren ABS-Pfad.
    Priorität: STAGING (fs.work_dir/<rel>) -> INPUT_ROOT/<rel> -> bereits absolut.
    """
    if os.path.isabs(pdf_path):
        return pdf_path if os.path.exists(pdf_path) else None

    # Relativ: zuerst im Staging
    if fs.session_id:
        staged_candidate = os.path.join(fs.work_dir, pdf_path)
        if os.path.exists(staged_candidate):
            return staged_candidate

    # Dann im Input
    input_candidate = os.path.join(INPUT_ROOT, pdf_path)
    if os.path.exists(input_candidate):
        return input_candidate

    return None


def summarize_pdf(pdf_path, model=None):
    """
    Analysiert eine PDF und erstellt eine 7-zeilige Summary.
    
    Args:
        pdf_path: Pfad zur PDF-Datei
        model: Optional - LLM-Modell (z.B. "mistral-nemo:latest")
               Falls None: Wird aus Flask Session geholt (für normale Requests)
               Falls übergeben: Wird direkt verwendet (für Background-Threads)
    
    Returns:
        str: 7-zeilige Summary oder Fallback
    """
    # Modell-Auswahl: Parameter > Session > Config-Default
    if model is None:
        try:
            model = session.get("selected_model", MODEL_LLM1)
        except RuntimeError:
            # Außerhalb Request-Context (z.B. Background-Thread ohne explizites Modell)
            log("⚠️ Kein Flask Request-Context und kein Modell übergeben, verwende Standard-Modell", level="warning")
            model = MODEL_LLM1
    # 1) Prompt laden
    try:
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            base_prompt = f.read().strip()
    except Exception as e:
        log(f"Fehler beim Laden des Prompts: {e}")
        return "Fehler beim Laden des Prompts"

    # 2) Pfad für Lesen auflösen (staging-aware)
    real_path = _resolve_path_for_read(pdf_path)
    if not real_path:
        log(f"PDF nicht gefunden (weder Staging noch Input): {pdf_path}")
        return "Fehler beim Öffnen der PDF"

    # 3) Öffnen
    try:
        doc = fitz.open(real_path)
    except Exception as e:
        log(f"Fehler beim Öffnen von {real_path}: {e}")
        return "Fehler beim Öffnen der PDF"

    num_pages = len(doc)
    if num_pages == 0:
        return "PDF hat keine Seiten"

    # 4) Erste-Seite-Textextrakt (toleranter)
    first_page_text = (doc[0].get_text() or "").strip()
    log(f"📄 [DEBUG] PDF: {os.path.basename(real_path)} - Seiten: {num_pages}, Text Seite 1: {len(first_page_text)} Zeichen")

    if len(first_page_text) < 10:
        if num_pages > 1:
            first_two = "\n".join((doc[0].get_text() or "", doc[1].get_text() or "")).strip()
            first_page_text = first_two
            log(f"📄 [DEBUG] Erweitert auf Seite 1+2: {len(first_page_text)} Zeichen")

        if len(first_page_text) < 10:
            log(f"⚠️ [DEBUG] Zu wenig Text gefunden ({len(first_page_text)} Zeichen) - Fallback auf 'Unbekannt'", level="warning")
            log(f"⚠️ [DEBUG] Textinhalt: '{first_page_text[:100]}'", level="warning")
            return "\n".join([
                "Unbekannt", "Unbekannt", "Unbekannt", "Unbekannt",
                "", "", "Keine Beschreibung verfügbar", "11"
            ])

    # 5) Kurzanalyse mit explizitem Modell
    short_prompt = f"{base_prompt}\n\n{first_page_text}"
    result = send_to_ollama(short_prompt, 0, model)  # ✅ Modell explizit übergeben
    
    if result is None:
        # Fallback: Volltext versuchen
        full_text = "\n".join(p.get_text() or "" for p in doc)
        result = send_to_ollama(f"{base_prompt}\n\n{full_text}", 1, model)
        if result is None:
            return "\n".join([
                "Unbekannt", "Unbekannt", "Unbekannt", "Unbekannt",
                "", "", "Keine Beschreibung verfügbar", "11"
            ])

    # Ergebnis auf 8 Zeilen normieren
    lines = [(s or "").strip() for s in (result or "").splitlines()]
    while len(lines) < 8:
        lines.append("")
    return "\n".join(lines[:8])