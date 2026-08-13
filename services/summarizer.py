import os
import pymupdf as fitz
from flask import session
from config import PROMPT_TEMPLATE, INPUT_ROOT, DEFAULT_MODEL
from .ollama_client import send_to_ollama
from .logger import log
from .file_utils import fs

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
            model = session.get("selected_model", DEFAULT_MODEL)
        except RuntimeError:
            # Außerhalb Request-Context (z.B. Background-Thread ohne explizites Modell)
            log("⚠️ Kein Flask Request-Context und kein Modell übergeben, verwende Standard-Modell", level="warning")
            model = DEFAULT_MODEL
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

    # 4) Seite auswählen: Deckblatt/Benachrichtigungsseite auf Seite 1 überspringen
    COVER_KEYWORDS = [
        "fax", "deckblatt", "faxnummer", "telefax", "fax-deckblatt", "faxseiten", "faxgerät",
        "scandatei", "iq4docs", "notificationservice", "followme.print",
        "automatisch generiert", "automatisch von", "scandatei von",
    ]
    # E-Mail-Benachrichtigungsseite erkennen: mind. 3 der 4 typischen E-Mail-Header vorhanden
    EMAIL_HEADERS = ["von:", "an:", "betreff:", "gesendet:"]
    start_page = 0
    first_page_text = (doc[0].get_text() or "").strip()
    log(f"📄 [DEBUG] PDF: {os.path.basename(real_path)} - Seiten: {num_pages}, Text Seite 1: {len(first_page_text)} Zeichen")

    if num_pages > 1:
        first_page_lower = first_page_text.lower()
        has_cover_keyword = any(kw in first_page_lower for kw in COVER_KEYWORDS)
        has_email_structure = sum(1 for h in EMAIL_HEADERS if h in first_page_lower) >= 3
        if has_cover_keyword or has_email_structure:
            reason = "Fax-Deckblatt" if has_cover_keyword else "E-Mail-Benachrichtigung"
            log(f"📠 {reason} auf Seite 1 erkannt - überspringe Seite 1, verwende Seite 2")
            start_page = 1
            first_page_text = (doc[1].get_text() or "").strip()
            log(f"📄 [DEBUG] Text Seite 2: {len(first_page_text)} Zeichen")

    if len(first_page_text) < 10:
        if num_pages > start_page + 1:
            first_page_text = "\n".join(
                (doc[start_page].get_text() or "", doc[start_page + 1].get_text() or "")
            ).strip()
            log(f"📄 [DEBUG] Erweitert auf Seite {start_page+1}+{start_page+2}: {len(first_page_text)} Zeichen")

        if len(first_page_text) < 10:
            log(f"⚠️ [DEBUG] Zu wenig Text gefunden ({len(first_page_text)} Zeichen) - Fallback auf 'Unbekannt'", level="warning")
            log(f"⚠️ [DEBUG] Textinhalt: '{first_page_text[:100]}'", level="warning")
            return "\n".join([
                "Unbekannt", "Unbekannt", "Unbekannt", "Unbekannt",
                "", "", "Keine Beschreibung verfügbar", "11"
            ])

    # 5) Kurzanalyse mit explizitem Modell
    short_prompt = f"{base_prompt}\n\n{first_page_text}"
    result = send_to_ollama(short_prompt, model)

    if result is None:
        # Fallback: Volltext ab gewählter Startseite versuchen
        full_text = "\n".join(p.get_text() or "" for p in doc[start_page:])
        result = send_to_ollama(f"{base_prompt}\n\n{full_text}", model)
        if result is None:
            return "\n".join([
                "Unbekannt", "Unbekannt", "Unbekannt", "Unbekannt",
                "", "", "Keine Beschreibung verfügbar", "11"
            ])

    # Wenn Seite 1 kein Fax-Deckblatt war aber trotzdem keine Patientendaten liefert:
    # Seite 2 als Fallback versuchen
    if start_page == 0 and num_pages > 1:
        result_lines = [(s or "").strip() for s in (result or "").splitlines()]
        def _is_empty(val): return not val or val.lower() == "unbekannt"
        name_leer = _is_empty(result_lines[0] if result_lines else "")
        vorname_leer = _is_empty(result_lines[1] if len(result_lines) > 1 else "")
        geb_leer = _is_empty(result_lines[2] if len(result_lines) > 2 else "")
        if name_leer and vorname_leer and geb_leer:
            page2_text = (doc[1].get_text() or "").strip()
            if len(page2_text) >= 10:
                log(f"⚠️ Seite 1 liefert keine Patientendaten - versuche Seite 2 als Fallback")
                result2 = send_to_ollama(f"{base_prompt}\n\n{page2_text}", model)
                if result2 is not None:
                    result = result2
                    log(f"✅ Seite 2 liefert Patientendaten - verwende Ergebnis von Seite 2")

    # Ergebnis auf 8 Zeilen normieren
    lines = [(s or "").strip() for s in (result or "").splitlines()]
    while len(lines) < 8:
        lines.append("")
    return "\n".join(lines[:8])