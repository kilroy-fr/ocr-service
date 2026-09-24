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
- **OCR:** Tesseract (via Subprocess), OCRmyPDF, Ghostscript
- **LLM:** Ollama – Standard-Modell `gemma4:12b` (`MODEL_LLM1` in `config.py`), Temperature 0.1
- **OCR-Fallback:** `glm-ocr:latest` (Vision), greift unter `OCR_FALLBACK_MIN_CHARS` Zeichen
- **PDF-Handling:** PyMuPDF, img2pdf
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
├── prompt.txt              # LLM-Prompt-Template (nicht als Volume gemountet!)
├── test_qualitaet.py       # 9 synthetische Testfälle, läuft vom Host
├── test_echte_briefe.py    # Echte Briefe durch die komplette Kette, läuft im Container
├── testdateien/            # Echte Patientenbriefe + erwartung.json (nicht im Repo/Image)
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

### OCR und Seitenauswahl
`ocr_pdf()` in `services/ocr.py` entscheidet **pro Seite**, ob OCR nötig ist
(`_pages_needing_ocr`): Seiten mit ≥ 200 Zeichen Textebene, ohne `U+FFFD` und ohne Bild über
mehr als die halbe Seite gelten als digital und behalten ihren Text. Nur die übrigen Seiten
gehen per `ocrmypdf --force-ocr --pages …` durch Tesseract; ist keine Seite ein Scan, läuft
`--skip-text`. Grund: `--force-ocr` auf digitalen Briefen ersetzte fehlerfreien Text durch
OCR-Fehler und mischte Briefkopf-Spalten in den Text. Ein reines `--skip-text` reicht nicht,
weil es auch Fax-Scans mit aufgedruckter Text-Kopfzeile übergehen würde.

Scans rendert `ocrmypdf` in ihrer nativen Auflösung. DPI-Anhebung, Median-Filter und
Sauvola-Binarisierung (der Ansatz aus ki-atteste) brachten hier keinen Gewinn – siehe
TESTERGEBNISSE.md.

`summarize_pdf()` schickt nur Seite 1 ans LLM. Sie wird als Deckblatt übersprungen, wenn sie
kürzer als 1000 Zeichen ist und ein Fax-/Scan-Stichwort enthält, oder mindestens drei
E-Mail-Header am Zeilenanfang hat. Ohne die Längengrenze fiel jede erste Briefseite mit
„Fax" im Briefkopf raus, und dem LLM fehlten Geburts- und Briefdatum.

Nach der LLM-Antwort leert `_drop_invented_dates()` Geburts- und Briefdatum, die nicht im
Text stehen, den das LLM bekommen hat. Alle getesteten Modelle außer gemma4:12b haben bei
fehlenden Angaben Daten erfunden; ein erfundenes Geburtsdatum ordnet den Brief in Medidok
dem falschen Patienten zu. Diese Prüfung nicht entfernen, auch nicht bei besseren Modellen.

### Kontextlänge (`num_ctx`)
`send_to_ollama()` setzt `num_ctx` pro Anfrage aus der Prompt-Länge (4k-Schritte, max. 16k).
Ist der Prompt länger als `num_ctx`, kürzt Ollama ihn **stillschweigend von vorne** – dann
fehlt die Anweisung, und das Modell kommentiert nur den Brieftext. Nie wieder feste kleine
Werte eintragen.

### Modell-Whitelist & gemma4-Sonderfall
Im Frontend wählbare Modelle sind in `routes/admin_routes.py` (`ALLOWED_MODELS`) auf eine
kuratierte Liste beschränkt (aktuell nur `gemma4:12b`). `/set_model` und der
`before_request`-Hook in `app.py` verwerfen nicht freigegebene Modelle, auch aus alten
Cookies. Auswahl und Ranking basieren auf `test_qualitaet.py` und `test_echte_briefe.py`,
Ergebnisse in [TESTERGEBNISSE.md](TESTERGEBNISSE.md). Wichtigstes Kriterium: Das Modell
darf fehlende Angaben nicht erfinden (Testfall T4) – ein erfundenes Geburtsdatum ordnet den
Brief in Medidok dem falschen Patienten zu. qwen3 fiel genau daran durch.

`gemma4:*`-Modelle verbrauchen ihr komplettes `num_predict`-Budget für unsichtbares
Reasoning und liefern über `/api/generate` eine leere Antwort. `services/ollama_client.py`
routet sie deshalb als einzige Modellfamilie über `/api/chat` mit `think: false` statt über
`/api/generate` – bei neuen `gemma4:*`-Varianten in der Whitelist immer testen, ob das noch
nötig ist.

### Tests mit echten Briefen
`testdateien/` enthält echte Arztbriefe, die mit Einwilligung der Patienten zu Test- und
Trainingszwecken verwendet werden dürfen. Sie stehen in `.gitignore` und `.dockerignore`.
Keine Namen, Geburtsdaten oder Adressen daraus in Code, Kommentare, Commits oder Doku
übernehmen – in TESTERGEBNISSE.md heißen sie Brief A/B/C.

```bash
docker cp test_echte_briefe.py ocr-web:/app/
docker cp testdateien ocr-web:/tmp/
docker exec -w /app ocr-web python test_echte_briefe.py /tmp/testdateien   # alle Whitelist-Modelle
docker exec ocr-web rm -rf /tmp/testdateien /app/test_echte_briefe.py      # danach aufräumen
```

---

## Entwicklung

### Lokal starten (Docker)
```bash
docker compose up --build
```
Hot-Reload ist aktiv: Quelldateien sind per Volume in den Container gemountet.
`prompt.txt` gehört **nicht** dazu – Prompt-Änderungen brauchen `docker compose up --build`.

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
- **PyMuPDF:** Immer `import pymupdf as fitz` – das Legacy-Modul `fitz` gibt seit
  PyMuPDF 1.28 beim Import eine Deprecation-Warnung aus. Der Alias hält alle
  bestehenden `fitz.*`-Aufrufe unverändert gültig.

---

## Abhängigkeiten & Docker-Image

Alle Pakete in `requirements.txt` sind exakt gepinnt und liefern für `python:3.12-slim`
fertige manylinux-Wheels. Das Image enthält **bewusst keinen Compiler** (kein `gcc`,
kein `python3-dev`) und auch keine Header-Pakete (`libjpeg-dev`, `zlib1g-dev`) – die
Pillow-Wheels bringen ihre Bibliotheken selbst mit. Das spart rund 320 MB.

`pip install` läuft deshalb mit `--only-binary=:all:`. Sollte ein Paket künftig kein
passendes Wheel mehr liefern, bricht der Build klar ab, statt undurchsichtig an einem
fehlenden `gcc` zu scheitern. In dem Fall entweder die Version anpassen oder die
Build-Abhängigkeiten gezielt wieder aufnehmen.

Beim Anheben von Versionen: `docker compose build` genügt nicht zum Prüfen – die
Wheels kommen erst beim Neubau der `pip`-Schicht. Nach Änderungen an `requirements.txt`
immer `docker compose up --build` fahren.

---

## Contributing

Beiträge sind willkommen! Bitte beachte die Coding-Konventionen oben und erstelle einen
Pull Request mit einer Beschreibung der Änderungen.
