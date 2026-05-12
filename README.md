# Medical OCR Service

Flask-basierter Dokumenten-Import-Service mit OCR und KI-gestützter Metadaten-Extraktion.
Verarbeitet medizinische Dokumente (PDF, Bilder, DOCX) per Tesseract OCR, extrahiert Metadaten
via LLM (Ollama) und reiht die Ergebnisse in eine Medidok-kompatible Import-Warteschlange ein.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-green)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **OCR** – Texterkennung für PDF und Bilddateien (optimiert für deutsche Dokumente)
- **LLM-Extraktion** – Automatische Metadaten-Erkennung (Patient, Absender, Datum, Fachrichtung) via Ollama
- **Staging-System** – Sichere Dateibearbeitung mit Commit/Rollback vor dem endgültigen Import
- **Import-Queue** – Sequenzielle Warteschlange für externe Import-Dienste (Medidok)
- **PDF-Bearbeitung** – Kombinieren, Splitten und Rotieren von PDFs
- **DOCX-Support** – Automatische Konvertierung und Verarbeitung von Word-Dokumenten
- **Live-Logging** – Echtzeit-Status via Server-Sent Events (SSE)
- **Dark Theme** – Modernes, dunkles UI-Design

## Architektur

```
Browser ──► Flask (Port 5000) ──► Tesseract OCR ──► LLM (Ollama)
                │                                        │
                ▼                                        ▼
         Staging-System ──► Import-Queue ──► Medidok-Verzeichnis
```

### Stack

| Komponente     | Technologie                          |
|----------------|--------------------------------------|
| Backend        | Python 3.12 / Flask 3.1              |
| OCR            | Tesseract (via Subprocess)           |
| LLM            | Ollama (z.B. `qwen2.5:14b`)         |
| PDF-Handling   | PyMuPDF, img2pdf, WeasyPrint         |
| DOCX           | python-docx                          |
| Deployment     | Docker + Docker Compose              |

## Voraussetzungen

- **Docker** und **Docker Compose**
- **Ollama** auf dem Host-System (oder erreichbar via Netzwerk) mit einem kompatiblen Modell
- **SMB/CIFS-Netzlaufwerk** (optional, für Medidok-Integration)

## Installation

### 1. Repository klonen

```bash
git clone https://github.com/kilroy-fr/ocr-service.git
cd ocr-service
```

### 2. Umgebungsvariablen konfigurieren

```bash
cp .env.example .env
```

Die `.env`-Datei anpassen:

```env
# SMB/CIFS-Netzlaufwerk (Pfad zum Medidok-Share)
SMB_SHARE=//server/Medidok
SMB_USERNAME=dein_username
SMB_PASSWORD=dein_passwort

# Flask Secret Key (zufälligen Wert verwenden!)
SECRET_KEY=ein-sicherer-zufaelliger-schluessel

# Startseiten-URL
HOME_URL=http://localhost:5000

# Zeitzone
TZ=Europe/Berlin
```

### 3. Ollama vorbereiten

Auf dem Host-System Ollama installieren und das Modell herunterladen:

```bash
# Ollama installieren: https://ollama.com
ollama pull qwen2.5:14b
```

### 4. Docker-Container starten

```bash
docker compose up --build -d
```

Der Service ist danach unter `http://localhost:5000` erreichbar.

## Verwendung

### Web-Oberfläche

1. **Dateien auswählen** – Dokumente vom Netzlaufwerk laden oder per Upload hochladen
2. **OCR starten** – Texterkennung und LLM-Analyse werden automatisch durchgeführt
3. **Metadaten prüfen** – Extrahierte Daten (Patient, Datum, Absender) kontrollieren und korrigieren
4. **Commit/Ablehnen** – Geprüfte Dokumente in die Import-Queue einreihen oder verwerfen

### Verzeichnisstruktur (Container)

| Verzeichnis            | Beschreibung                                    |
|------------------------|-------------------------------------------------|
| `/app/medidok/`        | Quelldateien vom Netzlaufwerk                   |
| `/app/medidok/staging/`| Session-Arbeitsverzeichnisse                    |
| `/app/medidok/output/` | Zwischenlager nach Commit, vor Import           |
| `/app/medidok/import/` | Import-Warteschlange für externen Dienst        |
| `/app/medidok/trash/`  | Papierkorb für verworfene Dateien               |
| `/app/medidok/errors/` | Fehlerfälle bei der Verarbeitung                |
| `/app/uploads/`        | Temporäre Uploads                               |

## Konfiguration

### LLM-Modell

Das Standard-Modell und die Ollama-URL werden in [config.py](config.py) konfiguriert:

```python
MODEL_LLM1  = "qwen2.5:14b"
OLLAMA_URL  = "http://host.docker.internal:11434/api/generate"
```

Im Docker-Setup verbindet sich der Container über `host.docker.internal` mit der
Ollama-Instanz auf dem Host. Für andere Setups die `OLLAMA_URL` entsprechend anpassen.

### Prompt-Template

Das LLM-Prompt-Template ist in [prompt.txt](prompt.txt) definiert und kann für andere
Dokumenttypen oder Sprachen angepasst werden.

## Entwicklung

### Mit Docker (empfohlen)

```bash
docker compose up --build
```

Hot-Reload ist aktiv: Quelldateien sind per Volume in den Container gemountet.
Änderungen an Python-Dateien und Templates werden automatisch übernommen.

### Ohne Docker (nur zum Testen)

```bash
pip install -r requirements.txt
python app.py
```

Erfordert Tesseract im PATH und Ollama auf `localhost:11434`.

## Projektstruktur

```
ocr-service/
├── app.py                  # Flask-App, OS-Patching, Startup-Lifecycle
├── config.py               # Pfade und Modell-Konfiguration
├── prompt.txt              # LLM-Prompt-Template
├── routes/
│   ├── main_routes.py      # Index, SSE-Stream
│   ├── file_routes.py      # Datei-Upload und -Auswahl
│   ├── control_routes.py   # OCR-Steuerung, Commit, Ablehnen
│   ├── analysis_routes.py  # LLM-Analyse-Endpunkte
│   └── admin_routes.py     # Admin-Funktionen
├── services/
│   ├── ocr.py              # OCR-Pipeline (Tesseract, Bild→PDF, LLM)
│   ├── import_queue.py     # Sequenzielle Import-Warteschlange
│   ├── file_utils.py       # Staging-Filesystem (StagingFS)
│   ├── session_manager.py  # Session-Registry
│   ├── ollama_client.py    # Ollama HTTP-Client
│   ├── summarizer.py       # PDF-Text-Extraktion für LLM
│   └── logger.py           # Zentrales Logging + SSE-Queue
├── static/                 # Frontend (JS, CSS)
├── templates/              # Jinja2-Templates
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Staging-System

Eine Besonderheit dieses Projekts ist das Staging-System: `app.py` patcht `os.rename`,
`os.remove` und `os.unlink` global, sodass alle Dateioperationen innerhalb des Eingabe-
verzeichnisses zunächst nur im **Staging-Manifest** geplant werden. Erst beim „Commit"
durch den Benutzer werden die Änderungen tatsächlich auf dem Dateisystem ausgeführt.
Dies verhindert versehentlichen Datenverlust bei der Verarbeitung medizinischer Dokumente.

## Lizenz

MIT License – siehe [LICENSE](LICENSE) für Details.
