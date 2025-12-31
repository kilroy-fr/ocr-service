# Übersicht: Notifications im OCR-Service

## app.js - Notifications

### ⚠️ Warnungen (warnings)

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 1 | Medidok-Analyse ohne Dateiauswahl | "Bitte mindestens eine Datei auswählen." | ✅ Ja | User-Fehler abfangen |
| 2 | Einzel-Analyse ohne Dateien | "Keine Dateien zum Analysieren vorhanden." | ✅ Ja | Verhindert leere Anfrage |
| 3 | Batch-Analyse ohne Dateien | "Keine Dateien zum Analysieren vorhanden." | ✅ Ja | Verhindert leere Anfrage |
| 4 | Combine < 2 Dateien (Medidok) | "Bitte mindestens zwei Dateien auswählen." | ✅ Ja | Funktional notwendig |
| 5 | Combine < 2 Dateien (Einzel) | "Bitte mindestens zwei Dateien auswählen." | ✅ Ja | Funktional notwendig |
| 6 | Combine < 2 Dateien (Batch) | "Bitte mindestens zwei Dateien auswählen." | ✅ Ja | Funktional notwendig |
| 7 | Split ohne Dateiauswahl (Medidok) | "Bitte genau eine Datei auswählen." | ✅ Ja | Funktional notwendig |
| 8 | Split ohne Dateiauswahl (Einzel) | "Bitte genau eine PDF-Datei auswählen." | ✅ Ja | Funktional notwendig |
| 9 | Split ohne Dateiauswahl (Batch) | "Bitte genau eine PDF-Datei auswählen." | ✅ Ja | Funktional notwendig |
| 10 | Split mit Nicht-PDF (Medidok) | "Nur PDF-Dateien können zerlegt werden." | ✅ Ja | Verhindert Fehler |
| 11 | Split mit Nicht-PDF (Einzel) | "Nur PDF-Dateien können zerlegt werden." | ✅ Ja | Verhindert Fehler |
| 12 | Split mit Nicht-PDF (Batch) | "Nur PDF-Dateien können zerlegt werden." | ✅ Ja | Verhindert Fehler |
| 13 | OCR ohne Dateiauswahl (Medidok) | "Bitte mindestens eine Datei auswählen." | ✅ Ja | User-Fehler abfangen |
| 14 | OCR ohne Dateiauswahl (Einzel) | "Bitte mindestens eine Datei auswählen." | ✅ Ja | User-Fehler abfangen |
| 15 | OCR ohne Dateiauswahl (Batch) | "Bitte mindestens eine Datei auswählen." | ✅ Ja | User-Fehler abfangen |

### ❌ Fehler (errors)

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 16 | Medidok-Analyse fehlgeschlagen | "Fehler beim Analysieren: ..." | ✅ Ja | Critical Error |
| 17 | Medidok-Analyse Netzwerkfehler | "Netzwerk-/JS-Fehler: ..." | ✅ Ja | Critical Error |
| 18 | Einzel-Analyse fehlgeschlagen | "Fehler beim Analysieren: ..." | ✅ Ja | Critical Error |
| 19 | Einzel-Analyse Netzwerkfehler | "Netzwerk-/JS-Fehler: ..." | ✅ Ja | Critical Error |
| 20 | Batch-Analyse fehlgeschlagen | "Fehler beim Analysieren: ..." | ✅ Ja | Critical Error |
| 21 | Batch-Analyse Netzwerkfehler | "Netzwerk-/JS-Fehler: ..." | ✅ Ja | Critical Error |
| 22 | Combine fehlgeschlagen (Medidok) | "Fehler beim Zusammenfassen: ..." | ✅ Ja | Operation fehlgeschlagen |
| 23 | Combine Netzwerkfehler (Medidok) | "Netzwerk-/JS-Fehler: ..." | ✅ Ja | Critical Error |
| 24 | Combine fehlgeschlagen (Einzel) | "Fehler beim Kombinieren: ..." | ✅ Ja | Operation fehlgeschlagen |
| 25 | Combine Netzwerkfehler (Einzel) | "Fehler: ..." | ✅ Ja | Critical Error |
| 26 | Combine fehlgeschlagen (Batch) | "Fehler beim Kombinieren: ..." | ✅ Ja | Operation fehlgeschlagen |
| 27 | Combine Netzwerkfehler (Batch) | "Fehler: ..." | ✅ Ja | Critical Error |
| 28 | Split fehlgeschlagen (Medidok) | "Fehler beim Zerlegen: ..." | ✅ Ja | Operation fehlgeschlagen |
| 29 | Split Netzwerkfehler (Medidok) | "Netzwerk-/JS-Fehler: ..." | ✅ Ja | Critical Error |
| 30 | Split fehlgeschlagen (Einzel) | "Fehler beim Zerlegen: ..." | ✅ Ja | Operation fehlgeschlagen |
| 31 | Split Netzwerkfehler (Einzel) | "Fehler: ..." | ✅ Ja | Critical Error |
| 32 | Split fehlgeschlagen (Batch) | "Fehler beim Zerlegen: ..." | ✅ Ja | Operation fehlgeschlagen |
| 33 | Split Netzwerkfehler (Batch) | "Fehler: ..." | ✅ Ja | Critical Error |
| 34 | OCR fehlgeschlagen (Medidok) | "Fehler beim OCR: ..." | ✅ Ja | Operation fehlgeschlagen |
| 35 | OCR Netzwerkfehler (Medidok) | "Netzwerk-/JS-Fehler: ..." | ✅ Ja | Critical Error |
| 36 | OCR fehlgeschlagen (Einzel) | "Fehler beim OCR: ..." | ✅ Ja | Operation fehlgeschlagen |
| 37 | OCR Netzwerkfehler (Einzel) | "Fehler: ..." | ✅ Ja | Critical Error |
| 38 | OCR fehlgeschlagen (Batch) | "Fehler beim OCR: ..." | ✅ Ja | Operation fehlgeschlagen |
| 39 | OCR Netzwerkfehler (Batch) | "Fehler: ..." | ✅ Ja | Critical Error |
| 40 | Upload fehlgeschlagen (Einzel) | "Fehler beim Upload: ..." | ✅ Ja | Critical Error |
| 41 | Upload Netzwerkfehler (Einzel) | "Netzwerk-/JS-Fehler: ..." | ✅ Ja | Critical Error |
| 42 | Upload fehlgeschlagen (Batch) | "Fehler beim Upload: ..." | ✅ Ja | Critical Error |
| 43 | Upload Netzwerkfehler (Batch) | "Netzwerk-/JS-Fehler: ..." | ✅ Ja | Critical Error |
| 44 | Modellwechsel fehlgeschlagen | "Fehler beim Setzen des Modells: ..." | ✅ Ja | User sollte informiert werden |
| 45 | Modellwechsel Netzwerkfehler | "Fehler beim Speichern der Modellauswahl" | ✅ Ja | Critical Error |

### ✅ Erfolg (success)

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 46 | Combine erfolgreich (Medidok) | "X Dateien zusammengefügt: ..." | ❓ Optional | User sieht Ergebnis in Preview |
| 47 | Combine erfolgreich (Einzel) | Console-Log only | ✅ Richtig | Keine Notification = gut |
| 48 | Combine erfolgreich (Batch) | Console-Log only | ✅ Richtig | Keine Notification = gut |
| 49 | Split erfolgreich (Medidok) | "PDF in X Einzelseiten zerlegt!..." | ❓ Optional | Staging-Liste zeigt Ergebnis |
| 50 | Split erfolgreich (Einzel) | "PDF in X Einzelseiten zerlegt!" | ❓ Optional | Staging-Liste zeigt Ergebnis |
| 51 | Split erfolgreich (Batch) | "PDF in X Einzelseiten zerlegt!" | ❓ Optional | Staging-Liste zeigt Ergebnis |

### ℹ️ Info (info/alert)

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 52 | OCR abgeschlossen (Medidok) | Detaillierte Statistik | ⚠️ Zu lang | Könnte gekürzt werden |
| 53 | OCR abgeschlossen (Einzel) | Detaillierte Statistik | ⚠️ Zu lang | Könnte gekürzt werden |
| 54 | OCR abgeschlossen (Batch) | Detaillierte Statistik | ⚠️ Zu lang | Könnte gekürzt werden |

### 🔄 Bestätigungen (confirm)

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 55 | Split PDF (Medidok) | "PDF '...' in einzelne Seiten zerlegen?" | ✅ Ja | Destruktive Operation |
| 56 | Split PDF (Einzel) | "PDF '...' in einzelne Seiten zerlegen?" | ✅ Ja | Destruktive Operation |
| 57 | Split PDF (Batch) | "PDF '...' in einzelne Seiten zerlegen?" | ✅ Ja | Destruktive Operation |
| 58 | OCR-Only (Medidok) | "X Datei(en) nur mit OCR verarbeiten?" | ❓ Optional | User hat Button geklickt |
| 59 | OCR-Only (Einzel) | "X Datei(en) nur mit OCR verarbeiten?" | ❓ Optional | User hat Button geklickt |
| 60 | OCR-Only (Batch) | "X Datei(en) nur mit OCR verarbeiten?" | ❓ Optional | User hat Button geklickt |

---

## control.js - Notifications

### ⚠️ Warnungen (warnings)

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 61 | Finalize ohne Entscheidungen | "Bitte treffen Sie für alle X Datei(en) eine Entscheidung..." | ✅ Ja | Verhindert unvollständige Daten |

### ❌ Fehler (errors)

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 62 | Rename fehlgeschlagen | "Fehler beim Umbenennen (Plan)." | ✅ Ja | Silent Error vermeiden |
| 63 | Finalize fehlgeschlagen | "Fehler: ..." | ✅ Ja | Critical Error |
| 64 | Finalize Exception | "Fehler beim Finalisieren: ..." | ✅ Ja | Critical Error |
| 65 | Abort fehlgeschlagen | "Fehler beim Abbrechen: ..." | ✅ Ja | Critical Error |

### ℹ️ Info

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 66 | Queue gestartet | "X Dateien werden sequenziell importiert..." | ❓ Optional | Queue-Monitor zeigt Status |

### 🔄 Bestätigungen (confirm)

| Nr | Trigger | Nachricht | Notwendig? | Kommentar |
|----|---------|-----------|------------|-----------|
| 67 | Abort All | "Alle Änderungen verwerfen...?" | ✅ Ja | Destruktive Operation |
| 68 | Queue komplett | "Alle X Dateien erfolgreich importiert!" | ✅ Ja | User-Feedback wichtig |
| 69 | Queue abbrechen (mit Dateien) | "ACHTUNG: Es sind noch X Datei(en)..." | ✅ Ja | Verhindert Datenverlust |
| 70 | Queue abbrechen (leer) | "X Datei(en) erfolgreich importiert..." | ✅ Ja | User-Feedback |
| 71 | Queue-Monitor beenden (Fallback) | "Queue-Monitoring beenden...?" | ✅ Ja | Sicherheitsabfrage |

---

## Empfehlungen für Vereinfachungen

### 🔴 Können entfernt werden:

1. **OCR-Only Confirms (#58-60)**: User hat Button geklickt, keine Bestätigung nötig
2. **Queue-Start Info (#66)**: Queue-Monitor zeigt Status, Notification überflüssig

### 🟡 Könnten gekürzt werden:

3. **OCR-Abschluss Messages (#52-54)**: Aktuell sehr lang mit Statistiken
   - Vorschlag: Nur Toast mit "X Dateien verarbeitet, Y erfolgreich"
   - Details in Console-Log

4. **Split Success (#49-51)**: Könnten kürzer sein
   - Aktuell: "PDF in X Einzelseiten zerlegt!\n\nDie Seiten wurden..."
   - Vorschlag: "PDF in X Einzelseiten zerlegt"

5. **Combine Success (#46)**: Könnte entfernt werden
   - Preview zeigt Ergebnis
   - Staging-Liste aktualisiert sich

### 🟢 Sollten bleiben:

- Alle Error-Notifications (kritisch für Debugging)
- Alle Warning-Notifications (verhindern User-Fehler)
- Alle Confirm-Dialoge für destruktive Operationen
- Queue-Completion-Bestätigungen

---

## Zusammenfassung

**Gesamt**: 71 Notifications
- **Notwendig**: 58 (82%)
- **Optional**: 8 (11%)
- **Zu lang**: 5 (7%)

**Optimierungspotenzial**:
- 2 Notifications entfernen
- 5 Notifications kürzen
- = 7 Verbesserungen möglich (10% Reduzierung)
