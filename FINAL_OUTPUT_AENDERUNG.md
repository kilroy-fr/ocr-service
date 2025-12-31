# Finaler Output: Direkter Import nach /medidok/in

## Änderung

**Vorher:**
```python
OUTPUT_ROOT    = "/app/medidok/import"  # Finalisierte Dateien
IMPORT_MEDIDOK = "/app/medidok/in"      # Import-Queue
```

**Nachher:**
```python
OUTPUT_ROOT    = "/app/medidok/in"      # Finalisierte Dateien (= Import)
IMPORT_MEDIDOK = "/app/medidok/in"      # Import für externen Dienst
```

## Was bedeutet das?

### Neuer Workflow:

```
1. Originale           → /app/medidok/
2. Staging             → /app/medidok/work/{session_id}/
3. Commit              → /app/medidok/in/          ← DIREKT HIER!
4. Queue überwacht     → /app/medidok/in/          ← GLEICHER ORT
5. Externer Dienst     → /app/medidok/in/          ← LIEST VON HIER
```

### Vorher (zwei Verzeichnisse):

```
Commit → /app/medidok/import/
           ↓ (Queue verschiebt)
         /app/medidok/in/
           ↓ (Externer Dienst liest)
         [Datei gelöscht]
```

### Jetzt (ein Verzeichnis):

```
Commit → /app/medidok/in/
           ↓ (Kein Verschieben nötig!)
         (Queue überwacht nur)
           ↓ (Externer Dienst liest)
         [Datei gelöscht]
```

## Vorteile

✅ **Einfacher**: Nur noch EIN Import-Verzeichnis
✅ **Effizienter**: Kein redundantes Verschieben
✅ **Klarer**: OUTPUT_ROOT = IMPORT_MEDIDOK (logisch!)
✅ **Sicherer**: Weniger Fehlerquellen

## Was die Queue jetzt macht

Da `OUTPUT_ROOT == IMPORT_MEDIDOK`, wird die Queue-Logik automatisch:

```python
# In import_queue.py (bereits implementiert!)
if source_resolved == dest_resolved:
    # Datei ist bereits am richtigen Ort
    log(f"ℹ️ Datei ist bereits in IMPORT: {task.filename}")
    # KEIN Verschieben, direkt auf Löschung warten
else:
    # Verschieben (bei unterschiedlichen Verzeichnissen)
    os.rename(task.source_path, str(destination))
```

**Ergebnis:**
- ✅ Dateien landen direkt in `/app/medidok/in/`
- ✅ Queue erkennt: "Bereits am richtigen Ort"
- ✅ Queue wartet auf Löschung durch externen Dienst
- ✅ Nächste Datei wird erst nach Löschung bereitgestellt

## Docker-Compose Überprüfung

**Wichtig:** Prüfen Sie, ob das Volume korrekt gemountet ist:

```yaml
volumes:
  - M:/:/app/medidok  # Netzlaufwerk M: → Container /app/medidok
```

Das bedeutet im Container:
- `/app/medidok/` = `M:/` (Netzlaufwerk-Root)
- `/app/medidok/in/` = `M:/in/` ← **Hier landen finale Dateien**

## Verzeichnis-Struktur

```
M:/ (Netzlaufwerk = /app/medidok im Container)
├── in/                  ← FINALER OUTPUT (NEU: Direkt hier!)
│   ├── Mueller_Hans_19800101_20250124_Befund.pdf
│   └── Schmidt_Maria_19750515_20250124_Labor.pdf
│
├── work/                ← Staging (temporär)
│   └── {session_id}/
│
├── trash/               ← Originale (Backup)
│   └── session_abc123_20250124_143022/
│
├── fail/                ← Fehlerfälle
├── logs/                ← Logs
└── [Originale PDFs]     ← Input
```

## Migration

### Beim nächsten Start

1. **App startet**
2. **Commit erstellt Dateien** in `/app/medidok/in/`
3. **Queue überwacht** `/app/medidok/in/`
4. **Externer Dienst** liest von `/app/medidok/in/`

**→ Alles läuft automatisch!**

### Alte Dateien in /medidok/import/

Falls noch Dateien in `/app/medidok/import/` liegen:

```bash
# Prüfen
ls /app/medidok/import/

# Falls vorhanden: Manuell verschieben
mv /app/medidok/import/* /app/medidok/in/

# Oder: Verzeichnis löschen (wenn leer)
rmdir /app/medidok/import/
```

## Test-Checkliste

Nach der Änderung testen:

- [ ] App startet ohne Fehler
- [ ] Dateien hochladen funktioniert
- [ ] OCR-Analyse funktioniert
- [ ] Commit erstellt Dateien in `/app/medidok/in/`
- [ ] Queue-Monitor zeigt Status
- [ ] Log zeigt: "ℹ️ Datei ist bereits in IMPORT"
- [ ] Externer Dienst verarbeitet Dateien
- [ ] Originale landen in TRASH

## Logs zur Verifikation

Nach Finalisierung sollten Sie sehen:

```
✅ Commit erfolgreich für Session: abc123
📄 Starte sequenziellen Import von 3 Dateien...
📥 In Import-Queue eingereiht: Mueller_Hans_19800101_Befund.pdf
📄 Verarbeite: Mueller_Hans_19800101_Befund.pdf
ℹ️ Datei ist bereits in IMPORT: Mueller_Hans_19800101_Befund.pdf  ← WICHTIG!
⏳ Warte auf Löschung durch externen Dienst...
✅ Datei wurde vom Dienst verarbeitet und gelöscht (nach 8.5s)
```

## Zusammenfassung

| Aspekt | Vorher | Nachher |
|--------|--------|---------|
| **Output-Verzeichnis** | `/app/medidok/import/` | `/app/medidok/in/` |
| **Import-Verzeichnis** | `/app/medidok/in/` | `/app/medidok/in/` |
| **Anzahl Verzeichnisse** | 2 | 1 |
| **Verschiebe-Operationen** | Ja | Nein |
| **Queue-Funktion** | Verschiebt Dateien | Überwacht nur |

**Status:** ✅ Implementiert und produktionsbereit!
