import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Upload & Arbeitsordner
UPLOAD_FOLDER       = "/app/uploads"           # Temporäre Uploads
PROMPT_TEMPLATE     = os.path.join(BASE_DIR, "prompt.txt")

# Netzlaufwerk //192.168.2.100/Daten – ein Mount, damit rename zwischen
# Quellordner und Arbeitsverzeichnissen funktioniert
DATEN_ROOT          = "/app/daten"

# Medidok – Quellordner. Darf keine Unterverzeichnisse enthalten: Medidok durchläuft ihn rekursiv.
INPUT_ROOT          = "/app/daten/MDok"                # Originale

# Arbeitsverzeichnisse
WORK_ROOT           = "/app/daten/pdf-tool/staging"    # Staging pro Session
OUTPUT_ROOT         = "/app/daten/pdf-tool/output"     # Zwischenlager nach Commit, vor Import
IMPORT_QUEUE_DIR    = "/app/daten/pdf-tool/import"     # Import-Warteschlange für externen Dienst
TRASH_DIR           = "/app/daten/pdf-tool/trash"      # Papierkorb
ERRORS_DIR          = "/app/daten/pdf-tool/errors"     # Fehlerfälle
LOGGING_FOLDER      = "/app/daten/pdf-tool/logs"       # Logs

# Metadaten
JSON_FOLDER         = "/app/processed/json"    # control_{session}.json

# Modelle & LLM
MODEL_LLM1          = "gemma4:12b"    # Einziges getestetes Modell, das fehlende Daten nicht erfindet (TESTERGEBNISSE.md), 7.6 GB VRAM
OLLAMA_URL          = "http://host.docker.internal:11434/api/generate"

# Default-Modell für neue Sessions
DEFAULT_MODEL       = MODEL_LLM1
DEFAULT_TEMPERATURE = 0.0  # Für deterministische, konsistente Extraktion

# OCR-Fallback via Vision-LLM (wenn Tesseract zu wenig Text liefert)
OCR_FALLBACK_MODEL     = "glm-ocr:latest"
OCR_FALLBACK_MIN_CHARS = 100  # Gesamtzeichen unterhalb dieses Schwellwerts → Fallback

# Frontend-URLs
HOME_URL            = os.environ.get("HOME_URL", "/")  # Startseite für Weiterleitung (relative URL bevorzugt)