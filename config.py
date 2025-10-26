import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Upload & allgemeine Arbeitsordner
UPLOAD_FOLDER       = "/app/uploads"        # temporäre Uploads (Einzel/Batch)
PROCESSED_FOLDER    = "/app/medidok/processed"      # Upload-Workflow-Zwischenergebnisse (optional beibehalten)
DATA_FOLDER         = os.path.join(BASE_DIR, "data")
PROMPT_TEMPLATE     = os.path.join(BASE_DIR, "prompt.txt")

# Medidok – klare Trennung nach neuem Staging-Flow
INPUT_ROOT          = "/app/medidok"   # 🔸 Originale (werden bis Commit NIE angefasst)
WORK_ROOT           = "/app/medidok/work"    # 🔸 Staging-Root (pro Session: work/<id>/staging/…)
OUTPUT_ROOT         = "/app/medidok/import" # 🔸 Ziel der Commits (finalisierte Dateien)
TRASH_DIR           = "/app/medidok/trash"   # 🗑️ Papierkorb für verarbeitete Originale

# bestehende Namen weiterhin exportieren, damit alter Code nicht bricht
SOURCE_DIR_MEDIDOK  = INPUT_ROOT              # Alias für Altkode
TARGET_DIR_MEDIDOK  = OUTPUT_ROOT             # Alias für Altkode

# Import & Fehler
IMPORT_MEDIDOK      = "/app/medidok/import"   # endgültiger Importordner
FAIL_DIR_MEDIDOK    = "/app/medidok/fail"     # Fehlerfälle
LOGGING_FOLDER      = "/app/medidok/logs"

# Metadaten (control_{session}.json)
JSON_FOLDER         = "/app/processed/json"

# Modelle & LLM
MODEL_LLM1          = "gpt-oss:20b"
MODEL_LLM2          = "hf.co/unsloth/medgemma-27b-text-it-GGUF:Q4_K_M"
OLLAMA_URL          = "http://host.docker.internal:11434/api/generate"

# Default-Modell für neue Sessions
DEFAULT_MODEL       = MODEL_LLM1  # Wird verwendet, wenn kein Cookie existiert
DEFAULT_TEMPERATURE = 0.2