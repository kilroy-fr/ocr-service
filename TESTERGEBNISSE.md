# LLM Modell-Test: Qualitaetsergebnisse

**Letzte Aktualisierung:** 20.09.2026
**Test:** Strukturierte Datenextraktion aus medizinischen Dokumenten (8 Felder)

---

## Testaufbau

### Testdokumente (9 Szenarien)

| ID | Name | Schwerpunkt |
|----|------|-------------|
| T1 | Arztbrief standard | Basisfall, einfache Struktur |
| T2 | Krankenhausentlassung | Absender = Einrichtung, Kategorie 6 |
| T3 | Laborbericht | Absender = Laborname, Fachrichtung Labor |
| T4 | Fehlende Informationen | Vorname/Datum fehlen – keine Halluzination erwartet |
| T5 | Komplexer Absendername | Akadem. Titel + Doppelname, nur Kernname erwartet |
| T6 | Adeliger Doppelname | "von der Heyden, Maria-Luise" – korrekte Zerlegung |
| T7 | Ausgeschr. Datum + 2 Aerzte | "8. Maerz 2025", erster Unterzeichner erwartet |
| T8 | Echter Brief (Text-PDF) | Aus `Test2.pdf` (digital erzeugt), kaputtes Umlaut-Encoding im Original |
| T9 | Echter Brief (Scan/OCR) | Aus `Test.pdf` (echter Scan), reale Tesseract-Fehler |

T8/T9 stammen aus echten Arztbriefen (`Test.pdf`/`Test2.pdf`, nicht im Repo, siehe `.gitignore`).
Patientendaten sind anonymisiert (Name/Geburtsdatum ersetzt), OCR-Rauschen bzw. das kaputte
Umlaut-Encoding aus den Originalen wurden bewusst beibehalten – das ist genau die Art von
Belastung, die synthetische Testfaelle nicht abbilden.

### Scoring

- **Felder 1-4, 8** (Nachname, Vorname, Gebdat, Briefdat, Kategorie): exakter Substring-Match
- **Felder 5-6** (Fachrichtung, Absender): Substring-Match
- **Feld 7** (Hauptbefund): mindestens 2 von 4 definierten Keywords = 1 Punkt, 1 Keyword = 0.5 Punkte
- **Fehlende Felder**: 1 Punkt wenn leer/Unbekannt geliefert, 0 Punkte wenn Daten erfunden
- **Maximum:** 8 Punkte pro Testdokument, 72 Punkte gesamt (9 Dokumente)

---

## Getestete Modelle

| Modell | Groesse (Disk) | Parameter |
|--------|-----------------|-----------|
| qwen3:8b | 5.2 GB | 8.2B |
| qwen3:14b | 9.3 GB | 14.8B |
| gemma4:12b | 7.6 GB | 11.9B |
| gemma4:e2b | 7.2 GB | 5.1B |
| deepseek-r1:14b | 9.0 GB | 14.8B |

Nicht mehr getestet, da bereits vorher aus der Whitelist entfernt (siehe "Aeltere Testrunden"
unten): qwen2.5:7b, qwen2.5:14b, gpt-oss:20b, gemma4:26b.

---

## Wichtiger Fund: gemma4-Familie braucht `/api/chat` statt `/api/generate`

Beim ersten Lauf mit `gemma4:12b` kam bei 5 von 9 Testfaellen **gar keine Antwort** zurueck
(`done_reason: length`, `eval_count: 2000`, aber `response` leer) – identisches Muster wie
seinerzeit bei `gemma4:26b`. Ursache ist **nicht** die Kontextlaenge (frueherer Verdacht),
sondern der Reasoning-Modus: `gemma4:12b`/`26b` verbrauchen ihr komplettes `num_predict`-Budget
fuer unsichtbares Thinking, bevor eine sichtbare Antwort folgt.

- Über `/api/generate` mit `think:false` bricht die Generierung sogar mit dem Fehler
  `prediction aborted, token repeat limit reached` ab.
- Über `/api/chat` mit `think:false` funktioniert die Unterdrueckung des Reasonings zuverlaessig.

**Fix angewendet in `services/ollama_client.py` und `test_qualitaet.py`:** Anfragen an
`gemma4:*`-Modelle laufen jetzt ueber `/api/chat` (Rollen-Message statt Rohprompt) mit
`think: false`, statt wie alle anderen Modelle ueber `/api/generate`. Ohne diesen Fix waere
`gemma4:12b` in der Produktion faktisch unbenutzbar gewesen (siehe `gemma4:e2b`, das den
Fehler seltener zeigt, da es deutlich kuerzer "denkt" – aber auch dort verbessert `/api/chat`
die Zuverlaessigkeit).

---

## Testergebnisse (aktuelle Prompt-Version, 20.09.2026)

| Modell | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | T9 | Summe | Pct |
|--------|----|----|----|----|----|----|----|----|----|-------|-----|
| **qwen3:8b** | +8 | +8 | +8 | -4 | +8 | +8 | +8 | +7 | +7 | 64.5/72 | **90%** |
| qwen3:14b | +8 | +8 | +8 | -4 | +8 | +8 | +8 | ~6 | ~5 | 62.0/72 | 86% |
| gemma4:12b | +8 | +8 | +8 | -1 | +8 | +7 | +8 | +8 | ~6 | 60.5/72 | 84% |
| gemma4:e2b | +8 | +7 | +8 | -3 | +8 | +8 | +8 | ~6 | ~5 | 59.0/72 | 82% |
| deepseek-r1:14b | +8 | -3 | ~6 | -4 | ~6 | -1 | +7 | +7 | -1 | 44.0/72 | 61% |

Legende: + = gut (>=7/8) ~ = mittel (5-6/8) - = schlecht (<5/8)

### Beobachtungen

**T4 – Fehlende Informationen (weiterhin universelles Problem)**
Alle Modelle erfinden Daten, wenn Felder fehlen, anstatt leere Zeilen zu liefern. Groesster
Qualitaetsrisikofaktor im Produktionsbetrieb, unveraendert gegenueber fruaheren Tests.

**T8/T9 – echte Dokumente sind schwerer als synthetische Testfaelle**
Kein Modell erreicht bei den echten Briefen die Werte der synthetischen Faelle. Haeufigster
Fehler: das kaputte Umlaut-Encoding in T8 ("Kr�ger" statt "Krüger") wird nicht zuverlaessig
aufgeloest, und in T9 verwechseln mehrere Modelle die im Fliesstext erwaehnte *neurologische*
Abklaerung mit der tatsaechlichen Fachrichtung des Absenders (Rheumatologie).

**deepseek-r1:14b – unzuverlaessig bei laengerem Reasoning**
Bei T6 und T9 lieferte das Modell keine geschlossene Antwort, sondern rohe `<think>`-Fragmente
("Alright, let's tackle this...", "The category is determined by..."), weil das Reasoning
innerhalb des `num_predict`-Budgets (400 Token) nicht abschliesst und der schliessende
`</think>`-Tag fehlt – die Strip-Regex in `ollama_client.py` greift dann nicht. Das ist kein
neues Problem des Modells, sondern zeigt sich mit dieser Doku-Menge und den beiden echten
Testfaellen deutlicher als zuvor. Mit 61% klar schwaechstes Modell im aktuellen Test,
zusaetzlich mit dem Risiko, rohe Denkfragmente statt Extraktion in die Import-Queue zu geben.
**Deshalb aus der Whitelist entfernt.**

**gemma4:12b – guter Neuzugang, sobald der /api/chat-Fix greift**
84% und damit klar vor `gemma4:e2b` (82%), bei akzeptabler Groesse (7.6 GB). Ohne den oben
beschriebenen Fix waere das Modell unbrauchbar gewesen.

**qwen3:8b – weiterhin bestes Modell**
90% im aktuellen Test, schnellste Inferenz alle Testfaelle (uebliche Antwortzeit < 1s bei
kurzen Dokumenten, ~5s beim laengsten Fall), niedrigster VRAM-Bedarf. Bleibt Standardmodell.

---

## Aktuelle Whitelist (`routes/admin_routes.py`)

```python
ALLOWED_MODELS = [
    "qwen3:8b",     # Standard, 90% Score, schnellste Inferenz
    "qwen3:14b",    # 86% Score
    "gemma4:12b",   # 84% Score (benoetigt /api/chat + think:False, siehe oben)
    "gemma4:e2b",   # 82% Score
]
```

Entfernt gegenueber der vorherigen Whitelist:
- **deepseek-r1:14b** (61%, unzuverlaessig bei laengerem Reasoning, siehe oben)
- **qwen2.5:7b, qwen2.5:14b, gpt-oss:20b** (von einem qwen3-Modell gleicher/kleinerer
  Groessenklasse klar geschlagen, siehe "Aeltere Testrunden")
- **gemma4:26b** (Totalausfall, siehe "Aeltere Testrunden")

---

## Empfehlungen fuer den Produktionsbetrieb

### Standard-Modell: qwen3:8b
Bestes Gesamtergebnis (90%) bei gleichzeitig schnellster Inferenz und niedrigstem VRAM-Bedarf
(5.2 GB) im gesamten Testfeld. Kein Modell im Test rechtfertigt einen Wechsel des Standards.

### Solide Alternativen: qwen3:14b, gemma4:12b
Beide liegen 4-6 Prozentpunkte hinter qwen3:8b, koennen aber als Zweitmeinung oder bei
Zweifelsfaellen im Frontend ausgewaehlt werden. gemma4:12b funktioniert nur korrekt mit dem
oben beschriebenen `/api/chat`-Fix.

### Offenes Problem: T4 (fehlende Felder)
Kein Modell beherrscht zuverlaessig leere Zeilen bei fehlenden Informationen. Empfehlung: Im
Backend nach der LLM-Antwort pruefen, ob extrahierte Daten plausibel sind (z.B.
Geburtsdatum-Format, Datumsbereich).

### Offenes Problem: Umlaut-Encoding in Quell-PDFs (T8)
Manche digital erzeugten PDFs liefern kaputte Umlaute (`W�rzburg` statt `Würzburg`) durch
fehlerhafte Font-Encodings. Kein getestetes Modell loest das zuverlaessig auf. Falls das in der
Praxis haeufiger vorkommt, lohnt sich eine Vorverarbeitung (Encoding-Reparatur vor dem Prompt)
statt sich auf das LLM zu verlassen.

---

## Aeltere Testrunden (Prompt v1/v2, 16.05.2026, 7 synthetische Testfaelle)

Damalige Whitelist umfasste zusaetzlich qwen2.5:7b, qwen2.5:14b, gpt-oss:20b und gemma4:26b.

| Modell | Score (Prompt v2) | Bewertung |
|--------|--------------------|-----------|
| qwen3:8b | 87% | Bestes Modell, wie im aktuellen Test bestaetigt |
| qwen3:14b | 86% | Bestaetigt |
| gemma4:e2b | 83% | Bestaetigt (82% im 9er-Test) |
| deepseek-r1:14b | 78% | Im 9er-Test auf 61% gefallen (siehe oben) |
| qwen2.5:7b | 77% | Entfernt: von qwen3:8b dominiert |
| gpt-oss:20b | 74% | Entfernt: von qwen3:14b dominiert, zudem langsam (20-30s) |
| qwen2.5:14b | 71% | Entfernt: von qwen3:14b dominiert, promptsensibel |
| gemma4:26b | 27% | Entfernt: Totalausfall (5/7 Tests ohne Antwort) – Ursache war vermutlich derselbe /api/generate-Reasoning-Bug wie bei gemma4:12b, siehe oben |

---

## Konfiguration

```python
# config.py
MODEL_LLM1 = "qwen3:8b"   # Standard, 90% Score, ~5.2 GB VRAM, Temperature 0.0
DEFAULT_TEMPERATURE = 0.0
```

---

*Tests durchgefuehrt: 16.05.2026 (7 Testfaelle) und 20.09.2026 (9 Testfaelle inkl. 2 echter
Arztbriefe) | Ollama via http://localhost:11434*
*Testskript: `test_qualitaet.py` (im Projektverzeichnis)*
