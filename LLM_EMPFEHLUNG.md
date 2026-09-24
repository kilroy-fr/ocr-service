# LLM-Empfehlung für strukturierte Datenextraktion

> Diese Datei fasst die Empfehlung zusammen. Die vollständigen Testdaten, Rohwerte je
> Testfall und Modell-Ranking stehen in [TESTERGEBNISSE.md](TESTERGEBNISSE.md).

## Aufgabenstellung

Aus medizinischen Dokumenten (PDFs, teils gescannt) exakt 8 Informationen extrahieren
(Nachname, Vorname, Geburtsdatum, Briefdatum, Fachrichtung, Absender, Hauptbefund,
Kategorie) – siehe [prompt.txt](prompt.txt). Format: strikt 8 Zeilen, keine Erklärungen.

## Empfehlung: gemma4:12b als Standard- und einziges Modell

`gemma4:12b` ist das einzige getestete Modell, das fehlende Angaben leer lässt, statt sie zu
erfinden (Testfall T4). Auf drei echten Arztbriefen (Test 24.09.2026) extrahiert es alle
Felder korrekt, bei den synthetischen Testfällen T1–T9 erreicht es 97 %. Antwortzeit ~1–2 s
pro Brief, 7.6 GB VRAM. Es ist als `MODEL_LLM1` / `DEFAULT_MODEL` in [config.py](config.py)
konfiguriert.

## Im Frontend wählbare Modelle (`routes/admin_routes.py`)

| Modell | Echte Briefe | T1–T9 | VRAM | Bemerkung |
|--------|------|------|------|-----------|
| **gemma4:12b** | 100 % | 97 % | 7.6 GB | Standard, braucht `/api/chat` + `think:false` (siehe unten) |

## Aus der Whitelist entfernt

- **qwen3:8b, qwen3:14b** (24.09.2026) – erfinden bei fehlenden Angaben Vorname,
  Geburtsdatum und Briefdatum, bei jeder getesteten Prompt-Variante und Temperatur
  (0.0–0.7). qwen3:8b übernimmt dabei sogar die Daten aus den Prompt-Beispielen. Ein
  erfundenes Geburtsdatum ordnet den Brief in Medidok dem falschen Patienten zu – auch wenn
  die OCR ein vorhandenes Datum nur nicht lesen konnte.
- **gemma4:e2b** (24.09.2026) – vertauscht Vor- und Nachname sowie Empfänger und Absender
  und lässt Zeilen aus, sodass alle folgenden Felder verrutschen.
- **deepseek-r1:14b** (61%) – liefert bei längerem Reasoning gelegentlich unfertige
  `<think>`-Fragmente statt der eigentlichen Extraktion (z.B. bei komplexen Namen oder
  echten Dokumenten). Risiko: rohe Denkfragmente landen in der Import-Queue.
- **qwen2.5:7b, qwen2.5:14b, gpt-oss:20b** – jeweils von einem qwen3-Modell gleicher
  oder kleinerer Größenklasse klar geschlagen (Qualität und/oder Geschwindigkeit).
- **gemma4:26b** – früher Totalausfall über `/api/generate`. Am 24.09.2026 mit `/api/chat`
  nachgetestet: echte Briefe 98 %, T1–T9 91 %, schreibt bei fehlenden Daten aber Platzhalter
  („01.01.1900“), schwankt zwischen Läufen und braucht 18 GB. Kein Vorteil ggü. gemma4:12b.

## Wichtiger technischer Hinweis: gemma4-Modelle brauchen `/api/chat`

`gemma4:12b`/`26b` verbrauchen ihr komplettes Token-Budget für unsichtbares Reasoning und
liefern über `/api/generate` eine leere Antwort (`done_reason: length`, aber
`response: ""`). Erst `/api/chat` mit `think: false` unterdrückt das Reasoning
zuverlässig. Ist in [services/ollama_client.py](services/ollama_client.py) und
[test_qualitaet.py](test_qualitaet.py) bereits umgesetzt – bei neuen `gemma4:*`-Varianten
in der Whitelist immer mit diesem Verhalten rechnen.

## Offene Punkte

- **Datumsprüfung (umgesetzt)**: `services/summarizer.py` leert Geburts- und Briefdatum,
  die nicht im Brieftext stehen. Das fängt erfundene Daten unabhängig vom Modell ab; ein
  leeres Feld erscheint als „Unbekannt“ und fällt in der Kontrolle auf.
- **Kaputte Umlaut-Encodings** in digital erzeugten PDFs: Seit digitale Seiten nicht mehr
  durch OCR laufen (siehe CLAUDE.md), kommt deren Textebene unverändert beim LLM an. Ob das
  in der Praxis noch vorkommt, zeigt sich im Betrieb.

## Wie testen

- `test_qualitaet.py` – 9 synthetische Fälle, läuft vom Host gegen `localhost:11434`.
- `test_echte_briefe.py` – echte Briefe aus `testdateien/` (nicht im Repo) durch die
  komplette Produktionskette inkl. OCR; läuft im Container, Aufruf siehe Docstring.

## Parameter (Temperature, top_p etc.)

Modellspezifische Optionen (inkl. der Sonderbehandlung für qwen3, deepseek-r1, gpt-oss,
gemma4) sind zentral in [services/ollama_client.py](services/ollama_client.py) gepflegt.
Diese Datei enthält keine eigene Kopie der Parameter mehr, um Drift zwischen Dokumentation
und Code zu vermeiden – bei Fragen zu konkreten Werten dort nachsehen.
