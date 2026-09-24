import os
import re
import pymupdf as fitz
from flask import session
from config import PROMPT_TEMPLATE, INPUT_ROOT, DEFAULT_MODEL
from .ollama_client import send_to_ollama
from .logger import log
from .file_utils import fs

# Deckblätter sind kurz. Ohne diese Grenze fliegt jede erste Briefseite raus, weil fast
# jeder Briefkopf "Fax" enthält – dann fehlen dem LLM Geburts- und Briefdatum, die meist
# nur auf Seite 1 stehen (gleiche Regel wie in ki-atteste).
_COVER_MAX_CHARS = 1000
# E-Mail-Benachrichtigung: mind. 3 der 4 Header am Zeilenanfang. Als reiner Substring
# trifft "an:" auch "Plan:" oder "Organ:".
_EMAIL_HEADER_RE = re.compile(r"^\s*(von|an|betreff|gesendet)\s*:", re.IGNORECASE | re.MULTILINE)

# Datumsangaben, wie sie in Briefen vorkommen: 01.02.1970, 1.2.70, 8. März 2025
_MONTHS = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "marz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}
_NUM_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s?\.\s?(\d{1,2})\s?\.\s?(\d{4}|\d{2})(?!\d)")
_WORD_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.?\s*(" + "|".join(_MONTHS) + r")\s*(\d{4})", re.IGNORECASE)
_LLM_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _dates_in_text(text: str) -> set:
    """Alle Datumsangaben im Text als (Tag, Monat, Jahr); zweistellige Jahre in beiden Jahrhunderten."""
    found = set()
    for d, m, y in _NUM_DATE_RE.findall(text):
        years = (1900 + int(y), 2000 + int(y)) if len(y) == 2 else (int(y),)
        found.update((int(d), int(m), year) for year in years)
    for d, month, y in _WORD_DATE_RE.findall(text):
        found.add((int(d), _MONTHS[month.lower()], int(y)))
    return found


def _drop_invented_dates(lines: list, source_text: str) -> None:
    """
    Leert Geburts- und Briefdatum (Zeile 3 und 4), wenn das Datum nicht im Brieftext steht.

    Auch gute Modelle erfinden gelegentlich Daten (gemma4:26b schrieb "01.01.1900", qwen3
    übernahm Daten aus den Prompt-Beispielen). Ein erfundenes Geburtsdatum ordnet den Brief
    in Medidok dem falschen Patienten zu – ein leeres Feld fällt dagegen in der Kontrolle auf.
    Hat das LLM ein von der OCR verstümmeltes Datum "repariert", wird es ebenfalls geleert.
    """
    dates = _dates_in_text(source_text)
    for idx, label in ((2, "Geburtsdatum"), (3, "Briefdatum")):
        value = lines[idx]
        if not value or value.lower() == "unbekannt":
            continue
        m = _LLM_DATE_RE.fullmatch(value)
        if m and (int(m[1]), int(m[2]), int(m[3])) in dates:
            continue
        log(f"⚠️ {label} '{value}' steht nicht im Brieftext – verworfen", level="warning")
        lines[idx] = ""


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
    start_page = 0
    first_page_text = (doc[0].get_text() or "").strip()
    log(f"📄 [DEBUG] PDF: {os.path.basename(real_path)} - Seiten: {num_pages}, Text Seite 1: {len(first_page_text)} Zeichen")

    if num_pages > 1:
        first_page_lower = first_page_text.lower()
        has_cover_keyword = (
            len(first_page_text) < _COVER_MAX_CHARS
            and any(kw in first_page_lower for kw in COVER_KEYWORDS)
        )
        has_email_structure = len({h.lower() for h in _EMAIL_HEADER_RE.findall(first_page_text)}) >= 3
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
    source_text = first_page_text  # Text, auf dem das Ergebnis beruht (für die Datumsprüfung)

    if result is None:
        # Fallback: Volltext ab gewählter Startseite versuchen
        full_text = "\n".join(p.get_text() or "" for p in doc[start_page:])
        result = send_to_ollama(f"{base_prompt}\n\n{full_text}", model)
        source_text = full_text
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
                    source_text = page2_text
                    log(f"✅ Seite 2 liefert Patientendaten - verwende Ergebnis von Seite 2")

    # Ergebnis auf 8 Zeilen normieren
    lines = [(s or "").strip() for s in (result or "").splitlines()]
    while len(lines) < 8:
        lines.append("")
    lines = lines[:8]
    _drop_invented_dates(lines, source_text)
    return "\n".join(lines)