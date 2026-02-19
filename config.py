import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Upload & Arbeitsordner
UPLOAD_FOLDER       = "/app/uploads"           # Temporäre Uploads
PROMPT_TEMPLATE     = os.path.join(BASE_DIR, "prompt.txt")

# Medidok – Hauptverzeichnisse
INPUT_ROOT          = "/app/medidok"           # Originale (Netzlaufwerk M:)
WORK_ROOT           = "/app/medidok/staging"   # Staging pro Session
OUTPUT_ROOT         = "/app/medidok/output"    # Zwischenlager nach Commit, vor Import
IMPORT_QUEUE_DIR    = "/app/medidok/import"    # Import-Warteschlange für externen Dienst
TRASH_DIR           = "/app/medidok/trash"     # Papierkorb
ERRORS_DIR          = "/app/medidok/errors"    # Fehlerfälle
LOGGING_FOLDER      = "/app/medidok/logs"      # Logs

# Metadaten
JSON_FOLDER         = "/app/processed/json"    # control_{session}.json

# Modelle & LLM
MODEL_LLM1          = "qwen2.5:14b"   # Optimiert für strukturierte Datenextraktion
OLLAMA_URL          = "http://host.docker.internal:11434/api/generate"

# Default-Modell für neue Sessions
DEFAULT_MODEL       = MODEL_LLM1
DEFAULT_TEMPERATURE = 0.0  # Für deterministische, konsistente Extraktion

# Frontend-URLs
HOME_URL            = "https://localhost"  # Startseite für Weiterleitung