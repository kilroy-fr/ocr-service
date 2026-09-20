# LLM-Empfehlung für strukturierte Datenextraktion

> Diese Datei fasst die Empfehlung zusammen. Die vollständigen Testdaten, Rohwerte je
> Testfall und Modell-Ranking stehen in [TESTERGEBNISSE.md](TESTERGEBNISSE.md).

## Aufgabenstellung

Aus medizinischen Dokumenten (PDFs, teils gescannt) exakt 8 Informationen extrahieren
(Nachname, Vorname, Geburtsdatum, Briefdatum, Fachrichtung, Absender, Hauptbefund,
Kategorie) – siehe [prompt.txt](prompt.txt). Format: strikt 8 Zeilen, keine Erklärungen.

## Empfehlung: qwen3:8b als Standardmodell

`qwen3:8b` ist im aktuellen Qualitätstest (9 Testfälle, davon 2 aus echten Arztbriefen)
mit 90% das beste Modell – bei gleichzeitig schnellster Inferenz (meist < 1s, ~5s beim
längsten Testfall) und dem niedrigsten VRAM-Bedarf (5.2 GB) im gesamten Testfeld. Es ist
bereits als `MODEL_LLM1` / `DEFAULT_MODEL` in [config.py](config.py) konfiguriert.

## Im Frontend wählbare Modelle (`routes/admin_routes.py`)

| Modell | Score | VRAM | Bemerkung |
|--------|-------|------|-----------|
| **qwen3:8b** | 90% | 5.2 GB | Standard |
| qwen3:14b | 86% | 9.3 GB | Solide Alternative, kein Qualitätsvorteil ggü. qwen3:8b |
| gemma4:12b | 84% | 7.6 GB | Braucht `/api/chat` + `think:false`, siehe unten |
| gemma4:e2b | 82% | 7.2 GB | Kleinstes Modell im Set, akzeptable Qualität |

Kein Modell im Test rechtfertigt einen Wechsel des Standards weg von `qwen3:8b`.

## Aus der Whitelist entfernt

- **deepseek-r1:14b** (61%) – liefert bei längerem Reasoning gelegentlich unfertige
  `<think>`-Fragmente statt der eigentlichen Extraktion (z.B. bei komplexen Namen oder
  echten Dokumenten). Risiko: rohe Denkfragmente landen in der Import-Queue.
- **qwen2.5:7b, qwen2.5:14b, gpt-oss:20b** – jeweils von einem qwen3-Modell gleicher
  oder kleinerer Größenklasse klar geschlagen (Qualität und/oder Geschwindigkeit).
- **gemma4:26b** – Totalausfall (siehe unten, gleicher Bug wie ursprünglich bei
  gemma4:12b).

## Wichtiger technischer Hinweis: gemma4-Modelle brauchen `/api/chat`

`gemma4:12b`/`26b` verbrauchen ihr komplettes Token-Budget für unsichtbares Reasoning und
liefern über `/api/generate` eine leere Antwort (`done_reason: length`, aber
`response: ""`). Erst `/api/chat` mit `think: false` unterdrückt das Reasoning
zuverlässig. Ist in [services/ollama_client.py](services/ollama_client.py) und
[test_qualitaet.py](test_qualitaet.py) bereits umgesetzt – bei neuen `gemma4:*`-Varianten
in der Whitelist immer mit diesem Verhalten rechnen.

## Offene Probleme (modellübergreifend)

- **Fehlende Felder**: Alle Modelle neigen dazu, fehlende Angaben (Vorname, Geburtsdatum,
  Briefdatum) zu erfinden statt eine leere Zeile zu liefern. Empfehlung: Plausibilitätsprüfung
  im Backend nach der LLM-Antwort (Datumsformat, Datumsbereich).
- **Kaputte Umlaut-Encodings** in manchen digital erzeugten Quell-PDFs (z.B. `W�rzburg`
  statt `Würzburg`) werden von keinem Modell zuverlässig aufgelöst.

## Parameter (Temperature, top_p etc.)

Modellspezifische Optionen (inkl. der Sonderbehandlung für qwen3, deepseek-r1, gpt-oss,
gemma4) sind zentral in [services/ollama_client.py](services/ollama_client.py) gepflegt.
Diese Datei enthält keine eigene Kopie der Parameter mehr, um Drift zwischen Dokumentation
und Code zu vermeiden – bei Fragen zu konkreten Werten dort nachsehen.
