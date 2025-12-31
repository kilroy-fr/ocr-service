# LLM-Empfehlung für strukturierte Datenextraktion

## Ihre Aufgabenstellung
- **Ziel**: Aus medizinischen Dokumenten (PDFs) exakt 7 Informationen extrahieren
- **Format**: Sehr strikt und konzentriert (7 Zeilen, keine Abweichungen)
- **Daten**: Name, Vorname, Geburtsdatum, Datum, Absender, Befund, Kategorie

## Ihre verfügbaren Modelle (via Ollama)

### 🎯 Top-Kandidaten für Ihre Aufgabe:
- ✅ **qwen2.5:14b** - BEREITS INSTALLIERT! (14.8B Parameter, Q4_K_M) - **BESTE WAHL**
- ✅ **qwen3:14b** - Neueste Version (14.8B Parameter, Q4_K_M)
- ✅ **qwen3:8b** - Schnellere Alternative (8.2B Parameter, Q4_K_M)
- ✅ **deepseek-r1:14b** - Reasoning-Modell (14.8B Parameter, basiert auf Qwen2)
- ⚠️ **gpt-oss:20b** - Aktueller Default (20.9B, MXFP4) - zu groß für diese Aufgabe

### 📊 Weitere verfügbare Modelle:
- llama3.1:8b / llama3.1:70b
- mistral-nemo:latest (12.2B)
- phi4:latest (14.7B)
- gemma2:9b / gemma2:27b / gemma3:4b / gemma3:12b
- medgemma-4b-it (medizinisch spezialisiert, aber klein)

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

### 🥈 **Alternative 1: Qwen3:14b (bereits installiert)**

**Warum Qwen3?**
- ✅ Neueste Version der Qwen-Familie
- ✅ Ähnliche Stärken wie Qwen2.5
- ✅ Möglicherweise besseres Reasoning
- ⚠️ Für reine Extraktion nicht unbedingt besser als 2.5

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

### 📊 **Modell-Vergleich für Ihre Aufgabe**

| Modell | Größe | VRAM | Geschwindigkeit | Format-Treue | Deutsch | Empfehlung |
|--------|-------|------|-----------------|--------------|---------|------------|
| **qwen2.5:14b** | 14.8B | ~9GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🥇 **BESTE WAHL** |
| **qwen3:14b** | 14.8B | ~9GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🥈 Test wert |
| **deepseek-r1:14b** | 14.8B | ~9GB | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 🥉 Komplex |
| **qwen3:8b** | 8.2B | ~5GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ Schnell |
| llama3.1:8b | 8.0B | ~5GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⚠️ Deutsch schwach |
| mistral-nemo | 12.2B | ~7GB | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⚠️ Nicht optimal |
| gpt-oss:20b | 20.9B | ~14GB | ⭐⭐ | ⭐⭐⭐ | ❓ | ❌ Zu groß |
| llama3.1:70b | 70.6B | ~43GB | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ❌ Viel zu groß |

## Optimale Parameter-Einstellungen

### Temperature
**Aktuelle Einstellung**: `0.2` ([config.py](config.py:36))

**Empfehlung für strukturierte Extraktion:**
```python
DEFAULT_TEMPERATURE = 0.0  # Oder maximal 0.1
```

**Begründung:**
- Bei Datenextraktion wollen Sie **deterministische** Ergebnisse
- Temperature = 0 eliminiert Zufälligkeit
- Konsistente Formatierung über alle Dokumente

### Weitere Parameter für ollama_client.py

Aktuell wird nur `model`, `prompt` und `stream` übergeben. Ich empfehle folgende Erweiterungen:

```python
def send_to_ollama(prompt, mnr, model, temperature=None):
    """
    Optimiert für strukturierte Datenextraktion
    """
    if temperature is None:
        temperature = session.get("temperature", 0.0)

    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'options': {
            'temperature': temperature,
            'top_p': 0.9,           # Reduziert Kreativität
            'top_k': 10,            # Begrenzt Token-Auswahl
            'repeat_penalty': 1.1,  # Verhindert Wiederholungen
            'num_predict': 150,     # Max. 7 Zeilen à ~20 Tokens
        }
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        log(f"Fehler bei der Anfrage an Ollama: {e}")
        return None
```

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
