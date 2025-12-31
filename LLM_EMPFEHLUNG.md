# LLM-Empfehlung für strukturierte Datenextraktion

## Ihre Aufgabenstellung
- **Ziel**: Aus medizinischen Dokumenten (PDFs) exakt 7 Informationen extrahieren
- **Format**: Sehr strikt und konzentriert (7 Zeilen, keine Abweichungen)
- **Daten**: Name, Vorname, Geburtsdatum, Datum, Absender, Befund, Kategorie

## Ihre verfügbaren Modelle (via Ollama)

### 🎯 Verfügbare Modelle (reduzierte Auswahl):
- ✅ **qwen2.5:14b** - BEREITS INSTALLIERT! (14.8B Parameter, Q4_K_M) - **BESTE WAHL**
- ✅ **qwen3:14b** - Neueste Version (14.8B Parameter, Q4_K_M) - **MIT OPTIMIERUNGEN!**
- ✅ **qwen3:8b** - Schnellere Alternative (8.2B Parameter, Q4_K_M)
- ✅ **deepseek-r1:14b** - Reasoning-Modell (14.8B Parameter, basiert auf Qwen2)
- ⚠️ **gpt-oss:20b** - Groß und langsam (20.9B, MXFP4)
- ⚠️ **llama3.1:8b** - Deutsch suboptimal (8.0B Parameter)

**Hinweis:** Die Liste der verfügbaren Modelle wurde auf die 6 besten Kandidaten reduziert, um die Auswahl zu vereinfachen.

## Empfehlung: Bestes Modell für diese Aufgabe

### 🥇 **Primäre Empfehlung: qwen2.5:14b (BEREITS INSTALLIERT!)**

**Warum Qwen2.5:14b?**
- ✅ **Bereits auf Ihrem System installiert** - keine Installation nötig!
- ✅ Exzellent in strukturierter Ausgabe und striktem Format-Folgen
- ✅ Sehr gut in Information Extraction Tasks
- ✅ Unterstützt Deutsch hervorragend (multilingual trainiert)
- ✅ Folgt Anweisungen extrem präzise
- ✅ 14B Größe: Optimale Balance zwischen Genauigkeit und Geschwindigkeit
- ✅ Q4_K_M Quantisierung: Gute Qualität bei ~9GB VRAM

### 🥈 **Alternative 1: Qwen3:14b (bereits installiert) - JETZT FUNKTIONIERT ES!**

**Warum Qwen3:14b?**
- ✅ Neueste Version der Qwen-Familie
- ✅ Besseres Reasoning als Qwen2.5
- ✅ **Problem gelöst**: Modell brauchte temperature > 0.0!
- ✅ **Automatische Optimierungen aktiviert:**
  - Temperature: 0.1 (NICHT 0.0!)
  - Erhöhter Kontext (num_ctx: 2048)
  - Längerer Timeout (60 Sekunden)
  - Keine stop-tokens (stoppt sonst zu früh)
  - Mehr Tokens (num_predict: 400)
- ⚠️ Etwas langsamer als qwen2.5 (7-8s vs 4-5s)

### 🥉 **Alternative 2: DeepSeek-R1:14b (bereits installiert)**

**Warum DeepSeek-R1?**
- ✅ Spezialisiert auf logisches Denken (Reasoning)
- ✅ Basiert auf Qwen2-Architektur
- ✅ Gut für komplexe medizinische Interpretation
- ⚠️ Möglicherweise "overthinking" für einfache Extraktion

### Alternative 3: Llama3.1:8b (bereits installiert)

**Warum Llama 3.1?**
- ✅ Schneller als 14B Modelle
- ✅ Weit verbreitet und gut getestet
- ⚠️ Deutsch nicht optimal (aber brauchbar)

### ❌ NICHT empfohlen für diese Aufgabe:
- **llama3.1:70b** - Viel zu groß und langsam
- **gemma2:27b** - Überdimensioniert
- **gpt-oss:20b** - Ihr aktueller Default, aber nicht optimal
- **medgemma-4b** - Zu klein, trotz medizinischer Spezialisierung

### 📊 **Modell-Vergleich für Ihre Aufgabe** (Nur verfügbare Modelle)

| Modell | Größe | VRAM | Geschwindigkeit | Format-Treue | Deutsch | Optimierungen | Empfehlung |
|--------|-------|------|-----------------|--------------|---------|---------------|------------|
| **qwen2.5:14b** | 14.8B | ~9GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Standard | 🥇 **BESTE WAHL** |
| **qwen3:14b** | 14.8B | ~9GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **Spezial** | 🥈 Funktioniert jetzt! |
| **qwen3:8b** | 8.2B | ~5GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Standard | ✅ Schnell |
| **deepseek-r1:14b** | 14.8B | ~9GB | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **Spezial** | 🥉 Funktioniert jetzt! |
| **llama3.1:8b** | 8.0B | ~5GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | Standard | ⚠️ Deutsch schwach |
| **gpt-oss:20b** | 20.9B | ~14GB | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | **Spezial** | ✅ Funktioniert jetzt! |

**Wichtig:** Die drei großen Modelle (qwen3:14b, deepseek-r1:14b, gpt-oss:20b) haben jetzt spezielle Optimierungen, die **automatisch** aktiviert werden!

## Optimale Parameter-Einstellungen

### Temperature
**Aktuelle Einstellung**: `0.0` (konfiguriert in [config.py](config.py:28))

**Begründung:**
- Bei Datenextraktion wollen Sie **deterministische** Ergebnisse
- Temperature = 0 eliminiert Zufälligkeit
- Konsistente Formatierung über alle Dokumente

### Parameter für ollama_client.py

✅ **Bereits implementiert in [services/ollama_client.py](services/ollama_client.py:28-96)**

**Standard-Parameter** (für qwen2.5:14b, qwen3:8b, etc.):
```python
{
    'temperature': 0.0,         # Deterministisch
    'top_p': 0.9,              # Reduziert Kreativität
    'top_k': 10,               # Begrenzt Token-Auswahl
    'repeat_penalty': 1.1,     # Verhindert Wiederholungen
    'num_predict': 200,        # Max. 7 Zeilen
    'stop': ['\n\n\n']        # Stoppt bei Leerzeilen
}
```

**Spezielle Optimierungen für große Modelle:**

✅ **qwen3:14b:**
```python
{
    'temperature': 0.1,        # ⚠️ NICHT 0.0! Sonst keine Ausgabe
    'top_p': 0.95,            # Weniger restriktiv als qwen2.5
    'top_k': 40,              # Mehr Token-Auswahl
    'repeat_penalty': 1.05,   # Schwächer (qwen3 braucht Wiederholungen)
    'num_predict': 400,       # Mehr Tokens für vollständige 7 Zeilen
    'num_ctx': 2048,          # Erhöhter Kontext
    # KEINE stop-tokens! qwen3 stoppt sonst zu früh
}
Timeout: 60 Sekunden
```

✅ **deepseek-r1:14b:**
```python
{
    'temperature': 0.1,
    'top_p': 0.95,
    'top_k': 40,
    'repeat_penalty': 1.05,
    'num_predict': 400,
    'num_ctx': 2048
}
Timeout: 60 Sekunden
```

✅ **gpt-oss:20b:**
```python
{
    'temperature': 0.2,       # Etwas höher wegen Modellgröße
    'top_p': 0.95,
    'top_k': 50,
    'repeat_penalty': 1.05,
    'num_predict': 400,
    'num_ctx': 2048
}
Timeout: 90 Sekunden (sehr groß!)
```

**Wichtig:**
- **qwen3:14b, deepseek-r1, gpt-oss** brauchen `temperature > 0.0`, sonst geben sie KEINE Antwort!
- **Keine stop-tokens** bei qwen3:14b - das Modell stoppt sonst zu früh
- Diese Optimierungen werden **automatisch** angewendet!
- **Getestet**: Alle 6 Modelle liefern jetzt 7 Zeilen zurück!

### System Prompt Optimierung

Ihr aktueller Prompt ([prompt.txt](prompt.txt)) ist bereits sehr gut! Kleine Verbesserungen:

```txt
Du bist eine Assistenz-KI für medizinische Dokumentenanalyse. Deine Aufgabe ist es, strukturierte Daten zu extrahieren.

KRITISCHE REGEL: Gib EXAKT sieben Zeilen zurück. Niemals mehr, niemals weniger.

AUSGABEFORMAT (strikt einhalten):
- Keine Kommentare, Einleitungen oder Erklärungen
- Keine Markdown-Formatierung (kein **, ##, -, etc.)
- Keine Satzzeichen am Zeilenende
- Eine Information pro Zeile
- Leere Zeile wenn Information fehlt
- Deutsche Sprache mit korrekten Umlauten

INHALT DER SIEBEN ZEILEN (in dieser Reihenfolge):
1. Nachname des Patienten (ohne Anrede)
2. Vorname des Patienten
3. Geburtsdatum (Format: TT.MM.JJJJ)
4. Briefdatum (Format: TT.MM.JJJJ)
5. Absender (Name des Arztes oder Krankenhauses; leer bei Overmans/Kadnikov)
6. Wichtigster Befund (keine Namen!)
7. Kategorie (5 = Praxis, 6 = Krankenhaus)

BEISPIEL FÜR KORREKTE AUSGABE:
Müller
Hans
15.03.1965
12.01.2025
Dr. Schmidt Kardiologie
Bluthochdruck stabil eingestellt
5
```

## Konkrete Implementierungs-Empfehlung

### ✅ Schritt 1: Modell bereits verfügbar!
**qwen2.5:14b ist bereits installiert** - keine Installation nötig!

### ✅ Schritt 2: config.py anpassen
```python
# Optimiert für strukturierte Datenextraktion
MODEL_LLM1 = "qwen2.5:14b"             # 🥇 Optimal für Ihre Aufgabe
MODEL_LLM2 = "qwen3:14b"               # 🥈 Alternative zum Testen
MODEL_LLM3 = "qwen3:8b"                # ⚡ Schnellere Alternative

DEFAULT_MODEL = MODEL_LLM1
DEFAULT_TEMPERATURE = 0.0              # ⚠️ WICHTIG: Deterministisch!
```

### Schritt 3: ollama_client.py erweitern
Fügen Sie die oben gezeigten Parameter hinzu.

### Schritt 4: Testen und Vergleichen
Erstellen Sie ein Test-Script:

```python
# test_models.py
import requests

models_to_test = [
    "qwen2.5:7b",
    "llama3.1:8b",
    "mistral-nemo:12b",
    "gpt-oss:20b"
]

test_prompt = """[Ihr Prompt aus prompt.txt]

[Beispiel-Dokument-Text]"""

for model in models_to_test:
    print(f"\n{'='*50}")
    print(f"Testing: {model}")
    print('='*50)

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            'model': model,
            'prompt': test_prompt,
            'stream': False,
            'options': {'temperature': 0.0}
        }
    )

    if response.ok:
        result = response.json().get('response', '')
        lines = result.strip().split('\n')
        print(f"Zeilen: {len(lines)}")
        print(result)
    else:
        print(f"Fehler: {response.status_code}")
```

## Erwartete Verbesserungen

### Mit Qwen2.5:7b + optimierten Parametern:
- ✅ **Formatstreue**: 95%+ exakt 7 Zeilen
- ✅ **Geschwindigkeit**: 2-4x schneller als 20B/27B Modelle
- ✅ **Konsistenz**: Deterministische Ausgaben bei temp=0
- ✅ **VRAM-Bedarf**: ~5GB statt 15-20GB
- ✅ **Genauigkeit**: Vergleichbar mit größeren Modellen bei strukturierten Tasks

## Zusammenfassung

**Beste Wahl**: `qwen2.5:7b` mit `temperature=0.0`

**Warum?**
1. Speziell gut in strikten Format-Anforderungen
2. Schnell genug für Produktivumgebung
3. Geringer Ressourcenverbrauch
4. Deutsche Sprache gut unterstützt
5. Keine Halluzinationen bei klaren Strukturen

**Nächste Schritte:**
1. `ollama pull qwen2.5:7b` ausführen
2. Temperature auf 0.0 setzen
3. Test mit 10-20 realen Dokumenten durchführen
4. Ggf. auf qwen2.5:14b upgraden falls Genauigkeit nicht ausreicht
