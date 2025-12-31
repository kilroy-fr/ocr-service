# Import Queue - Sequenzielle Dateiverarbeitung

## Problem

Der externe Medidok-Dienst, der Dateien aus dem `IMPORT_MEDIDOK` Verzeichnis einliest und verarbeitet, hat Probleme wenn:
- Mehrere Dateien gleichzeitig im Verzeichnis liegen
- Dateien von mehreren Patienten gleichzeitig verarbeitet werden müssen
- Zu viele Dateien hintereinander kommen

Dies führt zu Fehlern bei der Zuordnung und Integration in die Datenbank.

## Lösung

Die **Import Queue** stellt sicher, dass Dateien **sequenziell** dem externen Dienst präsentiert werden:

1. ✅ Dateien werden in eine Warteschlange eingereiht
2. ✅ Die erste Datei wird sofort in `IMPORT_MEDIDOK` verschoben
3. ✅ Der Service wartet, bis die Datei vom externen Dienst gelöscht wurde
4. ✅ Erst dann wird die nächste Datei verschoben
5. ✅ Der externe Dienst bekommt **immer nur eine Datei gleichzeitig**

## Architektur

### Komponenten

#### 1. ImportQueueService (`services/import_queue.py`)
- Verwaltet die Warteschlange von zu importierenden Dateien
- Läuft in einem separaten Background-Thread
- Überwacht das `IMPORT_MEDIDOK` Verzeichnis
- Wartet auf Löschung durch den externen Dienst

#### 2. Angepasste finalize_import Funktion (`routes/control_routes.py`)
- Verwendet die Import Queue anstelle direkter Dateiverschiebung
- Reiht alle Dateien in die Queue ein
- Gibt sofort eine Erfolgsmeldung zurück

#### 3. Status-Endpoint (`/import_queue_status`)
- Ermöglicht Überwachung des Import-Prozesses
- Zeigt aktuelle Queue-Größe und Statistiken

## Workflow

```
┌─────────────────┐
│  finalize_import │
│     Endpoint     │
└────────┬────────┘
         │
         │ Reiht Dateien ein
         ▼
┌─────────────────┐
│  Import Queue   │ ◄─── Wartet auf Löschung
│   (Service)     │
└────────┬────────┘
         │
         │ Verschiebt eine Datei
         ▼
┌─────────────────┐
│ IMPORT_MEDIDOK  │
│   Verzeichnis   │
└────────┬────────┘
         │
         │ Liest & löscht
         ▼
┌─────────────────┐
│ Externer Dienst │
│    (Medidok)    │
└─────────────────┘
```

## Verwendung

### 1. Normaler Import-Prozess

Der Import-Prozess läuft automatisch über die bestehende UI:

1. Dateien hochladen und analysieren
2. In Control-Panel umbenennen
3. "Finalisieren" klicken
4. ✨ Dateien werden **automatisch sequenziell** importiert

### 2. Status überwachen

**API-Aufruf:**
```bash
curl http://localhost:5000/import_queue_status
```

**Antwort:**
```json
{
  "success": true,
  "stats": {
    "total_queued": 15,
    "total_processed": 8,
    "total_failed": 0,
    "current_queue_size": 7,
    "current_file": "Mueller_Hans_19800101_20250124_Befund.pdf",
    "is_running": true
  }
}
```

### 3. Manuelles Monitoring

Im Log werden alle Schritte protokolliert:

```
📄 Starte sequenziellen Import von 10 Dateien...
📥 Datei in Import-Queue eingereiht: Mueller_Hans_19800101_20250124_Befund.pdf (Queue-Größe: 10)
📄 Verarbeite: Mueller_Hans_19800101_20250124_Befund.pdf (Session: abc123)
✅ Datei verschoben nach IMPORT: Mueller_Hans_19800101_20250124_Befund.pdf
⏳ Warte auf Löschung durch externen Dienst: Mueller_Hans_19800101_20250124_Befund.pdf
✅ Datei wurde vom Dienst verarbeitet und gelöscht: Mueller_Hans_19800101_20250124_Befund.pdf (nach 12.3s)
📄 Verarbeite: Schmidt_Maria_19750515_20250124_Labor.pdf (Session: abc123)
...
```

## Konfiguration

### Wartezeit-Timeout

Die maximale Wartezeit pro Datei ist konfigurierbar (Standard: 300 Sekunden = 5 Minuten):

```python
# In import_queue.py, Zeile 247
max_wait_seconds: int = 300
```

### Check-Intervall

Das Intervall für File-Watcher-Checks (Standard: 2 Sekunden):

```python
# Beim Erstellen des ImportQueueService
check_interval: float = 2.0
```

## Fehlerbehandlung

### Timeout beim Warten

Wenn eine Datei nach 5 Minuten noch nicht gelöscht wurde:
- ⚠️ Warnung im Log
- Die Queue fährt mit der nächsten Datei fort
- Statistik zählt als "failed"

### Datei nicht gefunden

Wenn eine Quelldatei nicht existiert:
- ❌ Fehler im Log
- Datei wird übersprungen
- Nächste Datei wird verarbeitet

### Service-Neustart

Bei App-Neustart:
- Queue wird geleert (noch nicht verschobene Dateien bleiben in OUTPUT_ROOT)
- Dateien in IMPORT_MEDIDOK bleiben unberührt
- Kein Datenverlust

## Vorteile

✅ **Keine Überlastung** des externen Dienstes
✅ **Weniger Fehler** bei der Zuordnung
✅ **Klare Reihenfolge** der Verarbeitung
✅ **Transparent** durch Status-Endpoint und Logging
✅ **Robust** durch Fehlerbehandlung und Timeouts
✅ **Keine Änderungen** am externen Dienst nötig

## Technische Details

### Threading-Sicherheit

- Verwendung von `threading.Lock()` für thread-sichere Operationen
- Queue-Operationen sind thread-safe durch `queue.Queue`
- Atomare Dateiverschiebung mit `os.rename()`

### Ressourcen-Verbrauch

- **Memory**: Minimal (nur Task-Metadaten in Queue)
- **CPU**: Sehr niedrig (Sleep zwischen Checks)
- **I/O**: Eine Datei nach der anderen

### Kompatibilität

- ✅ Windows & Linux
- ✅ Lokale Dateisysteme & Netzlaufwerke
- ✅ Keine zusätzlichen Dependencies
- ✅ Rückwärtskompatibel zu bestehendem Code

## Troubleshooting

### Problem: Queue läuft nicht

**Prüfen:**
```bash
curl http://localhost:5000/import_queue_status
```

**Lösung:**
- App neustarten
- Log überprüfen: `cat /app/medidok/logs/ocr-app.log`

### Problem: Dateien bleiben hängen

**Symptom:** Datei wird nicht gelöscht, Timeout nach 5 Minuten

**Mögliche Ursachen:**
1. Externer Dienst läuft nicht
2. Externer Dienst hat Fehler
3. Berechtigungsprobleme

**Lösung:**
1. Externen Dienst prüfen
2. Datei manuell aus IMPORT_MEDIDOK entfernen
3. Queue läuft automatisch weiter

### Problem: Queue läuft, aber keine Dateien werden verschoben

**Prüfen:**
- Sind Dateien in der Queue? `current_queue_size > 0`
- Ist ein File aktuell in Verarbeitung? `current_file != null`

**Lösung:**
- Status-Endpoint konsultieren
- Log-Dateien überprüfen

## Migration von Altcode

Die Umstellung erfolgt **transparent**:

### Vorher (direktes Verschieben):
```python
os.rename(src, dst)  # Alle Dateien sofort
```

### Nachher (Queue):
```python
import_queue.enqueue_file(src, filename, session_id)  # Sequenziell
```

**Keine Änderungen** an:
- UI/Frontend
- Datenbank-Schema
- Externem Dienst
- Benutzer-Workflow

## Weitere Optimierungen (Optional)

### Mögliche Erweiterungen:

1. **Priorisierung**: Bestimmte Patienten/Dateitypen vorziehen
2. **Retry-Logik**: Fehlgeschlagene Imports automatisch wiederholen
3. **Notification**: E-Mail/Webhook bei Abschluss
4. **Dashboard**: Web-UI für Queue-Monitoring
5. **Metrics**: Prometheus/Grafana Integration

## Support

Bei Fragen oder Problemen:
- Log-Dateien bereitstellen
- Status-Endpoint-Ausgabe teilen
- Beschreibung des erwarteten vs. tatsächlichen Verhaltens
