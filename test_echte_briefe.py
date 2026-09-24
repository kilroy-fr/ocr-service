#!/usr/bin/env python3
"""
Prüft die komplette Kette OCR → Seitenauswahl → LLM-Extraktion an echten Arztbriefen.

Die Briefe und die erwarteten Werte liegen in testdateien/ und sind nicht im Repo
(Patientendaten, siehe .gitignore/.dockerignore). Format von testdateien/erwartung.json:

    {
      "Brief.pdf": {
        "nachname": "Muster", "vorname": "Max",
        "geburtsdatum": "01.02.1970", "briefdatum": "03.04.2025",
        "fachrichtung": ["chirurg"], "absender": ["klinik x", "x-stadt"],
        "hauptbefund": ["prellung", "zeh"], "kategorie": "6"
      }
    }

Einzelwerte müssen exakt stimmen (ohne Groß-/Kleinschreibung), damit z.B.
"Muster Max" als Nachname auffällt. Bei Listen genügt eine der Alternativen als
Teilstring. Leerer String = Feld muss leer bleiben.

Läuft im Container, weil ocrmypdf/Tesseract und die Services gebraucht werden:

    docker cp test_echte_briefe.py ocr-web:/app/
    docker cp testdateien ocr-web:/tmp/
    docker exec -w /app ocr-web python test_echte_briefe.py /tmp/testdateien [--runs 3] [modell ...]

Ohne Modellangabe werden alle Modelle aus ALLOWED_MODELS (Dropdown) geprüft.
"""
import argparse
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.getcwd())

# Log-Ausgaben nicht ins Produktions-Log auf dem Netzlaufwerk schreiben
import config
config.LOGGING_FOLDER = tempfile.mkdtemp(prefix="ocr-test-log-")

from services.ocr import ocr_pdf                 # noqa: E402
from services.summarizer import summarize_pdf    # noqa: E402
from routes.admin_routes import ALLOWED_MODELS   # noqa: E402

FIELDS = ["nachname", "vorname", "geburtsdatum", "briefdatum",
          "fachrichtung", "absender", "hauptbefund", "kategorie"]


def score(got: str, expected) -> float:
    got = (got or "").strip().lower()
    if expected in ("", []):
        return 1.0 if got in ("", "unbekannt") else 0.0
    if isinstance(expected, list):
        return 1.0 if any(a.lower() in got for a in expected) else 0.0
    return 1.0 if got == expected.lower() else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verzeichnis")
    ap.add_argument("modelle", nargs="*")
    ap.add_argument("--runs", type=int, default=3, help="Wiederholungen je Modell und Brief")
    args = ap.parse_args()

    with open(os.path.join(args.verzeichnis, "erwartung.json"), encoding="utf-8") as f:
        expectations = json.load(f)
    models = args.modelle or ALLOWED_MODELS

    # OCR einmal pro Brief
    work = tempfile.mkdtemp(prefix="ocr-test-")
    ocr_files = {}
    for name in expectations:
        out = os.path.join(work, name.replace(".pdf", "_ocr.pdf"))
        t0 = time.time()
        if not ocr_pdf(os.path.join(args.verzeichnis, name), out):
            sys.exit(f"OCR fehlgeschlagen: {name}")
        ocr_files[name] = out
        print(f"OCR {name}: {time.time() - t0:.1f}s")

    totals = {}
    for model in models:
        print(f"\n{'=' * 70}\n{model}\n{'=' * 70}")
        points = possible = 0.0
        durations = []
        for name, exp in expectations.items():
            for run in range(args.runs):
                t0 = time.time()
                lines = summarize_pdf(ocr_files[name], model=model).split("\n")
                durations.append(time.time() - t0)
                lines += [""] * (8 - len(lines))
                scores = [score(lines[i], exp[f]) for i, f in enumerate(FIELDS)]
                points += sum(scores)
                possible += len(FIELDS)
                errors = [f"{FIELDS[i]}='{lines[i]}'" for i, s in enumerate(scores) if s < 1]
                print(f"  {name:<22} Lauf {run + 1}: {sum(scores):.0f}/8 ({durations[-1]:.1f}s)"
                      + (f"  FEHLER: {'; '.join(errors)}" if errors else ""))
                if run == 0:
                    print("      → " + " | ".join(lines[:8]))
        totals[model] = (points / possible * 100, sum(durations) / len(durations))

    print(f"\n{'=' * 70}\nERGEBNIS\n{'=' * 70}")
    for model, (pct, avg) in sorted(totals.items(), key=lambda x: -x[1][0]):
        print(f"  {model:<22} {pct:5.1f}%   Ø {avg:.1f}s")


if __name__ == "__main__":
    main()
