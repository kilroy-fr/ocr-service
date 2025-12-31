import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Upload & Arbeitsordner
UPLOAD_FOLDER       = "/app/uploads"           # Temporäre Uploads
DATA_FOLDER         = os.path.join(BASE_DIR, "data")
PROMPT_TEMPLATE     = os.path.join(BASE_DIR, "prompt.txt")

# Medidok – Hauptverzeichnisse
INPUT_ROOT          = "/app/medidok"           # Originale (Netzlaufwerk M:)
WORK_ROOT           = "/app/medidok/work"      # Staging pro Session
OUTPUT_ROOT         = "/app/medidok/in"        # Finalisierte Dateien (= Import)
IMPORT_MEDIDOK      = "/app/medidok/in"        # Import für externen Dienst (gleich wie OUTPUT_ROOT)
TRASH_DIR           = "/app/medidok/trash"     # Papierkorb
FAIL_DIR_MEDIDOK    = "/app/medidok/fail"      # Fehlerfälle
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