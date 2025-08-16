import os
import re
import fitz
from flask import session
from config import PROMPT_TEMPLATE, INPUT_ROOT
from .ollama_client import send_to_ollama
from .logger import log
from .file_utils import sanitize_filename, fs  # fs für work_dir (Staging)

def _resolve_path_for_read(pdf_path: str) -> str | None:
    """
    Nimmt REL- oder ABS-Pfad entgegen und liefert einen lesbaren ABS-Pfad.
    Priorität: STAGING (fs.work_dir/<rel>) -> INPUT_ROOT/<rel> -> bereits absolut.
    """
    if os.path.isabs(pdf_path):
        return pdf_path if os.path.exists(pdf_path) else None

    # Relativ: zuerst im Staging
    if fs.session_id:  # nur wenn Session aktiv ist
        staged_candidate = os.path.join(fs.work_dir, pdf_path)
        if os.path.exists(staged_candidate):
            return staged_candidate

    # Dann im Input
    input_candidate = os.path.join(INPUT_ROOT, pdf_path)
    if os.path.exists(input_candidate):
        return input_candidate

    return None

def summarize_pdf(pdf_path):
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
    if len(first_page_text) < 10:
        # Wenn kaum Text: nimm die ersten zwei Seiten zusammen – hilft bei dünnem OCR
        if num_pages > 1:
            first_two = "\n".join((doc[0].get_text() or "", doc[1].get_text() or "")).strip()
            first_page_text = first_two
        # Wenn immer noch zu dünn, gib eine knappe, aber gültige Struktur zurück
        if len(first_page_text) < 10:
            return "\n".join([
                "Unbekannt", "Unbekannt", "Unbekannt", "Unbekannt",
                "Kein Arzt erkannt", "Keine Beschreibung verfügbar", "11"
            ])

    # 5) Kurzanalyse
    short_prompt = f"{base_prompt}\n\n{first_page_text}"
    # Modellwahl erfolgt in send_to_ollama (Session oder Default); optional könnte man hier ein Modell übergeben:
    # model = session.get("selected_model")  # falls explizit nötig
    result = send_to_ollama(short_prompt, 0)
    if result is None:
        # Fallback: Volltext versuchen
        full_text = "\n".join(p.get_text() or "" for p in doc)
        result = send_to_ollama(f"{base_prompt}\n\n{full_text}", 1)
        if result is None:
            return "\n".join([
                "Unbekannt", "Unbekannt", "Unbekannt", "Unbekannt",
                "Kein Arzt erkannt", "Keine Beschreibung verfügbar", "11"
            ])

    # Ergebnis auf 7 Zeilen normieren
    lines = [(s or "").strip() for s in (result or "").splitlines()]
    while len(lines) < 7:
        lines.append("")
    return "\n".join(lines[:7])