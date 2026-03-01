# OCR Service – Entwicklerdokumentation

## Projektübersicht

Flask-basierter OCR-Dienst, der Dokumente (PDF, Bilder, DOCX) per Tesseract OCR verarbeitet,
per LLM (Ollama) Metadaten extrahiert und die Ergebnisse in eine Medidok-Import-Warteschlange
einreiht. Läuft als Docker-Container und bindet ein CIFS/SMB-Netzlaufwerk ein.

**Sprache:** Deutsch (UI, Logs, Kommentare, Commits)

---

## Architektur

### Stack
- **Backend:** Python 3.12 / Flask 3.1
- **OCR:** Tesseract (via Subprocess)
- **LLM:** Ollama – Standard-Modell `qwen2.5:14b`, Temperature 0.0
- **PDF-Handling:** PyMuPDF (fitz), img2pdf, WeasyPrint
- **DOCX:** python-docx
- **Deployment:** Docker + Docker Compose

### Verzeichnisstruktur
```
ocr-service/
├── app.py                  # Flask-App, OS-Patching, Startup-Lifecycle
├── config.py               # Alle Pfade und Modell-Konfiguration
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── prompt.txt              # LLM-Prompt-Template
├── routes/
│   ├── __init__.py         # register_routes()
│   ├── main_routes.py      # Index, SSE-Stream
│   ├── file_routes.py      # Datei-Upload, -Auswahl
│   ├── control_routes.py   # OCR-Steuerung, Commit, Ablehnen
│   ├── analysis_routes.py  # LLM-Analyse-Endpunkte
│   └── admin_routes.py     # Admin-Funktionen
├── services/
│   ├── ocr.py              # OCR-Pipeline (Tesseract, Bild→PDF, LLM)
│   ├── import_queue.py     # Sequenzielle Import-Warteschlange
│   ├── file_utils.py       # Staging-Filesystem (StagingFS), Hilfsfunktionen
│   ├── session_manager.py  # Session-Registry
│   ├── ollama_client.py    # Ollama HTTP-Client
│   ├── summarizer.py       # PDF-Text-Extraktion für LLM
│   ├── background_tasks.py # Hintergrundaufgaben
│   └── logger.py           # Zentrales Logging + SSE-Queue
├── static/
│   ├── app.js              # Haupt-Frontend-Logik
│   ├── control.js          # Steuerungs-UI
│   ├── queue_monitor.js    # Queue-Status-Monitor
│   ├── notifications.js    # Toast-Notifications
│   ├── file-sorting.js     # Dateilisten-Sortierung
│   └── style.css           # Dark-Theme-CSS
└── templates/
    ├── index.html          # Hauptseite
    └── control.html        # Steuerungsseite
```

---

## Wichtige Designentscheidungen

### Staging-System & OS-Patching
`app.py` patcht `os.rename`, `os.remove` und `os.unlink` global, sodass alle Dateioperationen
innerhalb von `INPUT_ROOT` zunächst nur im **Staging-Manifest** geplant werden. Erst beim
„Commit" werden sie tatsächlich ausgeführt.

- `fs` (StagingFS aus `services/file_utils.py`) ist das zentrale Objekt für alle Dateioperationen
- Für Operationen, die das Staging umgehen sollen (z.B. Startup-Cleanup), immer
  `_os_remove_original` / `_os_rename_original` verwenden
- **Nie** `os.rename`/`os.remove` direkt in Services aufrufen – diese sind gepatcht!

### Wichtige Pfade (aus `config.py`)
| Variable | Pfad | Beschreibung |
|---|---|---|
| `INPUT_ROOT` | `/app/medidok` | CIFS-Share (Netzlaufwerk) |
| `WORK_ROOT` | `/app/medidok/staging` | Staging pro Session |
| `OUTPUT_ROOT` | `/app/medidok/output` | Nach Commit, vor Import |
| `IMPORT_QUEUE_DIR` | `/app/medidok/import` | Für externen Import-Dienst |
| `TRASH_DIR` | `/app/medidok/trash` | Papierkorb |
| `ERRORS_DIR` | `/app/medidok/errors` | Fehlerfälle |
| `JSON_FOLDER` | `/app/processed/json` | `control_{session}.json` |
| `UPLOAD_FOLDER` | `/app/uploads` | Temporäre Uploads |

### Import-Queue (`services/import_queue.py`)
Stellt sicher, dass Dateien **sequenziell** in `IMPORT_QUEUE_DIR` erscheinen – die nächste
Datei wird erst eingereiht, wenn der externe Dienst die aktuelle gelöscht hat. Läuft als
Background-Thread. Datei-Bewegung über `_safe_move()` (CIFS-robust: copy2 + unlink statt rename).

### Live-Logging (SSE)
`/stream` liefert Server-Sent Events. `services/logger.py` schreibt in eine Queue, die der
SSE-Stream ausliest. Im Frontend werden Logs live angezeigt (`app.js`).

---

## Entwicklung

### Lokal starten (Docker)
```bash
docker compose up --build
```
Hot-Reload ist aktiv: Quelldateien sind per Volume in den Container gemountet.

### Direkt (ohne Docker, nur zum Testen)
```bash
pip install -r requirements.txt
python app.py
```
Erfordert Tesseract im PATH und Ollama auf localhost:11434.

### Umgebungsvariablen
Siehe `.env.example` für alle verfügbaren Konfigurationsoptionen.

---

## Coding-Konventionen

- **Sprache:** Deutsche Kommentare, Logs und Commit-Messages
- **Logging:** Immer `from services.logger import log` – nie `print()`
- **Dateioperationen in INPUT_ROOT:** Immer über `fs` (StagingFS) oder gepatchte os-Funktionen
- **Direkte OS-Operationen:** Nur `_os_rename_original` / `_os_remove_original` aus `file_utils`
- **LLM-Aufrufe:** Über `services/ollama_client.py`
- **Session-Kontext:** `fs.session_id` / `fs.work_dir` für sessionbezogene Pfade
- **Fehlerbehandlung:** Exceptions loggen, nicht still schlucken

---

## Contributing

Beiträge sind willkommen! Bitte beachte die Coding-Konventionen oben und erstelle einen
Pull Request mit einer Beschreibung der Änderungen.
