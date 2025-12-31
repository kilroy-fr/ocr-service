#!/usr/bin/env python3
"""
Test-Script zum Vergleichen verschiedener LLM-Modelle für strukturierte Datenextraktion.

Usage:
    python test_models.py [path_to_test_pdf]

Falls kein PDF angegeben wird, wird ein Beispieltext verwendet.
"""

import sys
import os
import requests
import json
import fitz  # PyMuPDF
from datetime import datetime
from pathlib import Path

# Ollama API URL
OLLAMA_URL = "http://localhost:11434/api/generate"

# Modelle zum Testen (verfügbare Modelle auf Ihrem System)
MODELS_TO_TEST = [
    "qwen2.5:14b",      # 🥇 Empfehlung
    "qwen3:14b",        # 🥈 Alternative
    "qwen3:8b",         # ⚡ Schnell
    "deepseek-r1:14b",  # 🧠 Reasoning
    "llama3.1:8b",      # Baseline
    # "gpt-oss:20b",    # Zu groß/langsam - auskommentiert
]

# Prompt aus prompt.txt
PROMPT_TEMPLATE = """Du bist eine Assistenz-KI für medizinische Dokumentenanalyse. Deine Aufgabe ist es, strukturierte Daten zu extrahieren.

KRITISCHE REGEL: Gib EXAKT sieben Zeilen zurück. Niemals mehr, niemals weniger.

AUSGABEFORMAT (strikt einhalten):
- Keine Kommentare, Einleitungen oder Erklärungen
- Keine Markdown-Formatierung (kein **, ##, -, etc.)
- Keine Satzzeichen am Zeilenende
- Eine Information pro Zeile
- Leere Zeile wenn Information fehlt
- Deutsche Sprache mit korrekten Umlauten

INHALT DER SIEBEN ZEILEN (in dieser Reihenfolge):
1. Nachname des Patienten (ohne Anrede)
2. Vorname des Patienten
3. Geburtsdatum (Format: TT.MM.JJJJ)
4. Briefdatum (Format: TT.MM.JJJJ)
5. Absender (Name des Arztes oder Krankenhauses; leer bei Overmans/Kadnikov)
6. Wichtigster Befund (keine Namen!)
7. Kategorie (5 = Praxis, 6 = Krankenhaus)

BEISPIEL FÜR KORREKTE AUSGABE:
Müller
Hans
15.03.1965
12.01.2025
Dr. Schmidt Kardiologie
Bluthochdruck stabil eingestellt
5"""


# Beispiel-Dokument-Text (falls kein PDF angegeben)
EXAMPLE_DOCUMENT = """
Gemeinschaftspraxis Dr. Schmidt & Dr. Weber
Kardiologie - Innere Medizin
Musterstraße 123
12345 Musterstadt

Datum: 15.01.2025

Arztbrief

Sehr geehrte Kollegin, sehr geehrter Kollege,

Patient: Müller, Hans
Geburtsdatum: 12.03.1965

Diagnose:
Der oben genannte Patient stellte sich am 15.01.2025 in unserer Praxis vor.

Befunde:
- Blutdruck: 135/85 mmHg (unter Medikation)
- EKG: Sinusrhythmus, keine pathologischen Veränderungen
- Labor: Cholesterin leicht erhöht (240 mg/dl)

Beurteilung:
Die arterielle Hypertonie ist unter der aktuellen Medikation (Ramipril 5mg)
gut eingestellt. Das Cholesterin sollte weiter beobachtet werden.

Mit freundlichen kollegialen Grüßen

Dr. med. Schmidt
Facharzt für Kardiologie
"""


def extract_pdf_text(pdf_path):
    """Extrahiert Text aus der ersten Seite eines PDFs."""
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            return None

        # Erste Seite
        first_page_text = doc[0].get_text().strip()

        # Falls zu wenig Text, auch zweite Seite nehmen
        if len(first_page_text) < 100 and len(doc) > 1:
            first_page_text += "\n" + doc[1].get_text().strip()

        return first_page_text
    except Exception as e:
        print(f"❌ Fehler beim Lesen der PDF: {e}")
        return None


def test_model(model_name, prompt, document_text, temperature=0.0):
    """
    Testet ein einzelnes Modell.

    Returns:
        dict: Ergebnis mit 'response', 'lines', 'duration', 'error'
    """
    full_prompt = f"{prompt}\n\n{document_text}"

    payload = {
        'model': model_name,
        'prompt': full_prompt,
        'stream': False,
        'options': {
            'temperature': temperature,
            'top_p': 0.9,
            'top_k': 10,
            'repeat_penalty': 1.1,
            'num_predict': 200,
            'stop': ['\n\n\n'],
        }
    }

    print(f"\n{'='*60}")
    print(f"🧪 Testing: {model_name}")
    print('='*60)

    start_time = datetime.now()

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=60
        )

        duration = (datetime.now() - start_time).total_seconds()

        if not response.ok:
            return {
                'model': model_name,
                'error': f"HTTP {response.status_code}",
                'duration': duration,
                'response': None,
                'lines': 0
            }

        result_text = response.json().get('response', '').strip()
        lines = result_text.split('\n')
        line_count = len(lines)

        # Ausgabe
        print(f"⏱️  Dauer: {duration:.2f}s")
        print(f"📏 Zeilen: {line_count} {'✅' if line_count == 7 else '❌ (sollte 7 sein!)'}")
        print(f"\n📄 Antwort:")
        print("-" * 60)
        for i, line in enumerate(lines, 1):
            print(f"{i}. {line if line else '(leer)'}")
        print("-" * 60)

        return {
            'model': model_name,
            'response': result_text,
            'lines': line_count,
            'duration': duration,
            'error': None,
            'correct_format': line_count == 7
        }

    except requests.exceptions.Timeout:
        duration = (datetime.now() - start_time).total_seconds()
        print(f"⏱️  Timeout nach {duration:.2f}s")
        return {
            'model': model_name,
            'error': 'Timeout',
            'duration': duration,
            'response': None,
            'lines': 0
        }
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        print(f"❌ Fehler: {e}")
        return {
            'model': model_name,
            'error': str(e),
            'duration': duration,
            'response': None,
            'lines': 0
        }


def print_summary(results):
    """Druckt eine Zusammenfassung aller Testergebnisse."""
    print(f"\n\n{'='*80}")
    print("📊 ZUSAMMENFASSUNG")
    print('='*80)

    print(f"\n{'Modell':<25} {'Dauer':<10} {'Zeilen':<8} {'Format OK':<12} {'Status'}")
    print("-" * 80)

    for r in results:
        model = r['model']
        duration = f"{r['duration']:.2f}s" if r['duration'] else "N/A"
        lines = str(r['lines'])
        format_ok = "✅ Ja" if r.get('correct_format', False) else "❌ Nein"
        status = "✅ OK" if not r['error'] else f"❌ {r['error']}"

        print(f"{model:<25} {duration:<10} {lines:<8} {format_ok:<12} {status}")

    print("\n" + "="*80)

    # Beste Wahl
    successful = [r for r in results if not r['error'] and r.get('correct_format', False)]
    if successful:
        fastest = min(successful, key=lambda x: x['duration'])
        print(f"\n🏆 Schnellstes Modell (mit korrektem Format): {fastest['model']} ({fastest['duration']:.2f}s)")

    format_correct = [r for r in results if r.get('correct_format', False)]
    if format_correct:
        print(f"✅ Modelle mit korrektem 7-Zeilen-Format: {len(format_correct)}/{len(results)}")
    else:
        print("⚠️  WARNUNG: Kein Modell hat exakt 7 Zeilen zurückgegeben!")


def main():
    """Hauptfunktion - führt alle Tests durch."""
    print("🚀 LLM-Modell-Vergleich für strukturierte Datenextraktion")
    print("="*80)

    # PDF oder Beispieltext?
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if not os.path.exists(pdf_path):
            print(f"❌ Datei nicht gefunden: {pdf_path}")
            sys.exit(1)

        print(f"📄 Verwende PDF: {pdf_path}")
        document_text = extract_pdf_text(pdf_path)

        if not document_text:
            print("❌ Konnte keinen Text aus PDF extrahieren")
            sys.exit(1)
    else:
        print("📄 Verwende Beispiel-Dokument (keine PDF angegeben)")
        document_text = EXAMPLE_DOCUMENT

    print(f"📝 Dokument-Länge: {len(document_text)} Zeichen")
    print(f"🧪 Teste {len(MODELS_TO_TEST)} Modelle mit Temperature=0.0")

    # Alle Modelle testen
    results = []
    for model in MODELS_TO_TEST:
        result = test_model(model, PROMPT_TEMPLATE, document_text, temperature=0.0)
        results.append(result)

    # Zusammenfassung
    print_summary(results)

    # Ergebnisse in JSON speichern
    output_file = "model_comparison_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Ergebnisse gespeichert in: {output_file}")


if __name__ == "__main__":
    main()
