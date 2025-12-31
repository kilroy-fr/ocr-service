# Bugfix: Queue-Monitor & Einzeldatei-Probleme

## Probleme

### Problem 1: Queue-Monitor zeigt Fehler bei einzelner Datei
**Symptom:** Monitor zeigt "Warte auf Queue-Service..." auch wenn Import läuft

**Ursache:** Einzelne Datei wird so schnell verarbeitet, dass Queue bereits leer ist wenn Monitor startet

### Problem 2: "Abbrechen" Button unklar
**Symptom:** User unsicher was passiert wenn er abbricht

**Ursache:** Keine Warnung wenn noch Dateien in Queue

### Problem 3: OUTPUT_ROOT = IMPORT_MEDIDOK
**Symptom:** Dateien werden "nicht verschoben"

**Ursache:** Beide Verzeichnisse identisch → `os.rename(src, src)` macht nichts!

## Lösungen implementiert

### ✅ Fix 1: Robustere Completion-Erkennung

**Datei:** [static/control.js](static/control.js:737-771)

**Änderung:**
```javascript
// VORHER: Crash wenn Queue schon leer
if (current_queue_size === 0 && total_processed === total_queued && total_queued > 0)

// NACHHER: Flag für Aktivitäts-Tracking
let hasSeenActivity = false;

if (total_queued > 0 || current_queue_size > 0) {
    hasSeenActivity = true;
}

// Nur Success wenn wir Aktivität gesehen haben
if (hasSeenActivity && current_queue_size === 0 && total_processed > 0 && ...)
```

**Vorteile:**
- ✅ Wartet bis Queue wirklich aktiv war
- ✅ Zeigt Success nur wenn Dateien verarbeitet wurden
- ✅ Kein Fehler bei schneller Verarbeitung

**Check-Intervall verbessert:**
- VORHER: 5 Sekunden
- NACHHER: 3 Sekunden (schnelleres Feedback)

### ✅ Fix 2: Intelligenter "Abbrechen" Button

**Datei:** [static/control.js](static/control.js:773-807)

**Änderung:**
```javascript
// VORHER: Einfache Bestätigung
if (confirm('Wirklich beenden?'))

// NACHHER: Statusabhängige Warnung
if (current_queue_size > 0) {
    alert(`⚠️ ACHTUNG: Es sind noch ${current_queue_size} Datei(en) in der Warteschlange!

${total_processed} Datei(en) wurden bereits importiert.

Wenn Sie jetzt abbrechen, werden die verbleibenden Dateien NICHT importiert.`)
} else {
    alert(`${total_processed} Datei(en) wurden erfolgreich importiert.`)
}
```

**Vorteile:**
- ✅ User weiß genau was passiert
- ✅ Warnung wenn noch Dateien offen
- ✅ Success-Meldung wenn alles fertig

### ✅ Fix 3: Queue-Logik für identische Verzeichnisse

**Datei:** [services/import_queue.py](services/import_queue.py:156-203)

**Problem identifiziert:**
```python
# In config.py
OUTPUT_ROOT = "/app/medidok/import"
IMPORT_MEDIDOK = "/app/medidok/import"
# → Beide identisch!
```

**Änderung:**
```python
# Prüfe ob Quelle und Ziel identisch sind
source_resolved = Path(task.source_path).resolve()
dest_resolved = destination.resolve()

if source_resolved == dest_resolved:
    # Datei ist bereits am richtigen Ort
    log(f"ℹ️ Datei ist bereits in IMPORT: {task.filename}")
    # Keine Verschiebung, direkt auf Löschung warten
else:
    # Normal verschieben
    _os_real.rename(task.source_path, str(destination))
    log(f"✅ Datei verschoben nach IMPORT: {task.filename}")
```

**Vorteile:**
- ✅ Funktioniert auch wenn OUTPUT_ROOT = IMPORT_MEDIDOK
- ✅ Keine fehlgeschlagenen `rename` Aufrufe
- ✅ Klarere Logs ("bereits in IMPORT" statt Fehler)

## Test-Szenarien

### ✅ Szenario 1: Einzelne Datei
```
1. Eine Datei auswählen und finalisieren
2. Monitor startet
3. Datei wird schnell verarbeitet (< 3 Sekunden)
4. Monitor zeigt Status korrekt
5. Success-Dialog erscheint
```

### ✅ Szenario 2: Viele Dateien mit Abbruch
```
1. 10 Dateien finalisieren
2. Monitor zeigt: "3 in Queue, 7 verarbeitet"
3. User klickt "Abbrechen"
4. Warnung: "⚠️ Noch 3 Dateien in Queue!"
5. User kann entscheiden
```

### ✅ Szenario 3: Dateien bereits in IMPORT
```
1. Dateien sind nach Commit bereits in /app/medidok/import
2. Queue startet
3. Log zeigt: "ℹ️ Datei ist bereits in IMPORT"
4. Wartet auf Löschung durch Dienst
5. Nächste Datei
```

## Datei-Lebenszyklus (vereinfacht)

```
Original (INPUT_ROOT)
    ↓ [Finalisieren]
TRASH (gesichert)

Verarbeitet (OUTPUT_ROOT = IMPORT_MEDIDOK)
    ↓ [Queue: Warte auf Löschung]
Vom externen Dienst gelöscht
    ↓
Nächste Datei
```

**Wichtig:**
- ✅ Originale sind **sofort im TRASH** (beim Finalisieren)
- ✅ Queue wartet auf **Löschung** (nicht auf Verschiebung)
- ✅ Monitor läuft auch wenn User zur Startseite geht

## Was sich NICHT ändert

- ✅ Import-Logik bleibt gleich
- ✅ Sequenzielle Verarbeitung funktioniert weiter
- ✅ Externer Dienst bekommt nur eine Datei
- ✅ API-Endpunkte bleiben unverändert

## Empfehlung für die Zukunft

### Optional: Separate Verzeichnisse

Um die Logik klarer zu machen:

```python
# In config.py ändern:
OUTPUT_ROOT = "/app/medidok/staging"    # NEU: Separates Staging
IMPORT_MEDIDOK = "/app/medidok/import"  # Import-Verzeichnis
```

**Vorteile:**
- Klarere Trennung
- Dateien werden **wirklich verschoben**
- Einfacher zu debuggen

**Nachteile:**
- Erfordert Änderung in Docker-Compose (neues Volume)
- Breaking Change

**→ NICHT notwendig** - aktuelle Lösung funktioniert!

## Deployment

Die Änderungen sind bereits implementiert:

**Geänderte Dateien:**
1. ✅ [static/control.js](static/control.js) - Zeile 737-807
2. ✅ [services/import_queue.py](services/import_queue.py) - Zeile 156-203

**Keine Config-Änderungen nötig!**

```bash
# Einfach neustarten:
python app.py
```

## Zusammenfassung

| Problem | Status | Lösung |
|---------|--------|--------|
| Monitor zeigt Fehler bei schneller Datei | ✅ Fixed | Aktivitäts-Flag + schnellere Checks |
| "Abbrechen" Button unklar | ✅ Fixed | Statusabhängige Warnung |
| OUTPUT_ROOT = IMPORT_MEDIDOK | ✅ Fixed | Skip wenn Quelle = Ziel |

**Ergebnis:**
- ✅ Monitor funktioniert mit 1 oder 100 Dateien
- ✅ User bekommt klare Rückmeldungen
- ✅ Queue funktioniert auch mit identischen Verzeichnissen

## Support

Falls weiterhin Probleme:

1. **Logs prüfen:**
   ```bash
   tail -f /app/medidok/logs/ocr-app.log
   ```

2. **Queue-Status prüfen:**
   ```bash
   curl http://localhost:5000/import_queue_status
   ```

3. **TRASH prüfen:**
   ```bash
   ls -la /app/medidok/trash/
   # Sollte Originale enthalten
   ```

**Vollständige Dokumentation:** [DATEI_LEBENSZYKLUS.md](DATEI_LEBENSZYKLUS.md)
