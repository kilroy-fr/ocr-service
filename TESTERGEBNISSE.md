# LLM Modell-Test: Qualitaetsergebnisse

**Letzte Aktualisierung:** 24.09.2026
**Test:** Strukturierte Datenextraktion aus medizinischen Dokumenten (8 Felder)

---

## Testrunde 24.09.2026: echte Arztbriefe (`testdateien/`)

### Ergebnis in Kuerze

- **Einziges freigegebenes Modell: `gemma4:12b`** (jetzt auch Standard). Echte Briefe 100%,
  T1-T9 97%, und als einziges Modell laesst es fehlende Angaben leer (T4).
- **qwen3:8b und qwen3:14b entfernt**: Bei fehlenden Angaben erfinden sie Vorname,
  Geburtsdatum und Briefdatum, und zwar bei jeder getesteten Prompt-Variante und Temperatur.
- **gemma4:e2b entfernt**: vertauscht Vor- und Nachname sowie Empfaenger und Absender und
  laesst Zeilen aus, sodass alle folgenden Felder verrutschen.
- **gemma4:26b nachgetestet, nicht aufgenommen**: laeuft seit dem `/api/chat`-Fix (echte
  Briefe 98%, T1-T9 91%), schreibt bei fehlenden Daten aber Platzhalter wie "01.01.1900" und
  ist in keinem Punkt besser als gemma4:12b.
- **Neue Datumspruefung** in `summarizer.py`: Geburts- und Briefdatum, die nicht im Brieftext
  stehen, werden geleert – faengt erfundene Daten modellunabhaengig ab.
- Die grossen Gewinne kamen nicht vom Modell, sondern von **OCR, Seitenauswahl und
  Kontextlaenge** (siehe "Was die Fehler verursacht hat").

### Testdokumente

Drei echte Briefe, mit Einwilligung der Patienten zu Test- und Trainingszwecken freigegeben.
Sie liegen nicht im Repo und nicht im Docker-Image (`.gitignore`, `.dockerignore`), ebenso
die erwarteten Werte in `testdateien/erwartung.json`.

| Brief | Art | Stolpersteine |
|-------|-----|---------------|
| A | Radiologie-Praxis, MRT-Befund, digital erzeugtes PDF | Patient und Empfaengerpraxis tragen denselben Nachnamen; Absender steht nur im Briefkopf, die Unterschrift ist ein Bild |
| B | Klinik, chirurgischer Notaufnahmebericht, Scan 200 dpi Graustufen | Briefdatum im Kopf verblasst und unlesbar; ein Assistenzarzt unterschreibt |
| C | Universitaetsklinikum, Rheumatologie, 3 Seiten, Farbscan 600 dpi | Patientin ist zugleich Empfaengerin; "Fax" im Briefkopf; Vorstellungsdatum ungleich Briefdatum |

Testskript: `test_echte_briefe.py`. Es prueft die komplette Produktionskette
(`ocr_pdf` → `summarize_pdf` → Ollama) und muss deshalb im Container laufen
(Aufruf siehe Docstring). Bewertung: Name, Geburtsdatum, Briefdatum und Kategorie exakt;
Fachrichtung, Absender und Hauptbefund als Teilstring aus einer Liste zulaessiger Begriffe.
3 Laeufe je Modell und Brief; die Antworten waren in allen Laeufen identisch.

### Ergebnis echte Briefe (Anteil korrekter Felder)

| Modell | vorher (Stand 7aa26b2) | + OCR/Deckblatt/Kontext | + neuer Prompt |
|--------|------|------|------|
| gemma4:12b | 71% | 96% | **100%** |
| qwen3:14b | 65% | 96% | 100% |
| qwen3:8b | 54% | 88% | 100% |
| gemma4:e2b | 50% | 79% | 88% |

Die ersten beiden Spalten wurden noch mit Teilstring-Vergleich fuer Namen bewertet; mit der
strengen Bewertung laegen sie bei gemma4:e2b noch niedriger ("Nachname Vorname" in der Nachnamen-Zeile
zaehlte dort als Treffer).

### Was die Fehler verursacht hat

1. **Deckblatt-Erkennung** (`summarizer.py`, Brief C): Seite 1 wurde verworfen, sobald "fax"
   darin vorkam – das steht in fast jedem Briefkopf. Das LLM bekam dann nur Seite 2 mit
   Laborwerten, ohne Geburts- und Briefdatum. Jetzt gilt wie in ki-atteste: Deckblatt nur bei
   weniger als 1000 Zeichen, E-Mail-Header nur am Zeilenanfang.
2. **Kontextfenster 2048 bei qwen3** (`ollama_client.py`): Ist der Prompt laenger, kuerzt
   Ollama ihn stillschweigend von vorne. Gemessen: Laborseite mit 2290 Tokens wurde auf 1026
   gekuerzt, die Anweisung fehlte, und qwen3 antwortete "Deine Laborwerte sind sehr
   umfassend ...". `num_ctx` richtet sich jetzt nach der Prompt-Laenge (4k-Schritte, max. 16k).
3. **`--force-ocr` auf digitalen PDFs** (`ocr.py`, Brief A): OCR ersetzte fehlerfreien Text
   durch OCR-Text. Eine ganze Zeile des Adressfelds fehlte, "L4" wurde zu "LA", "li." zu "Ii.",
   und Briefkopf-Spalten wurden in den Text gemischt. Jetzt laufen nur Seiten ohne brauchbare
   Textebene durch Tesseract (siehe CLAUDE.md, Abschnitt OCR).
4. **Prompt**: Empfaenger als Absender, Vorstellungs- statt Briefdatum, Klinik-Notaufnahme als
   Praxis (Kategorie 5), unterschreibender Assistenzarzt statt Klinik als Absender. Behoben mit
   Regeln "WER IST WER", "BRIEFDATUM", "KATEGORIE", einem Beispiel mit leeren Zeilen und einer
   abschliessenden Zeile `DOKUMENT:`. Die klare Trennung zwischen Anweisung und Brieftext war
   entscheidend: Erst damit fanden qwen3:8b und gemma4:e2b bei Brief A den richtigen Absender.
   Konkrete Beispieldaten in den Regeln (z.B. `*01.01.1980`) wurden von qwen3 als Wert
   uebernommen und sind deshalb durch Platzhalter ersetzt.

### OCR: Vergleich mit dem ki-atteste-Ansatz

ki-atteste gewann durch 300 statt 144 dpi plus Median-Filter. Hier rendert `ocrmypdf` Scans
bereits in ihrer nativen Aufloesung (Brief B 200 dpi, Brief C 600 dpi), das Problem gibt es
also nicht. Getestet an B und C: `--oversample 300`, `--tesseract-thresholding sauvola`, ohne
`--clean`, sowie Tesseract direkt mit 300 dpi Graustufen und Median 3×3. Die Unterschiede
waren jeweils einzelne Zeichen, keine Variante war in Summe besser; Sauvola erzeugte mehr
Rauschen aus den Randbarcodes. Das verblasste Datum in Brief B konnte keine Variante lesen.
Die Scan-Parameter bleiben deshalb unveraendert.

### Synthetische Tests T1-T9 mit neuem Prompt

Dabei einen Bewertungsfehler in `test_qualitaet.py` behoben: `evaluate()` warf leere Zeilen
weg. Liess ein Modell ein fehlendes Feld korrekt leer, rutschten alle folgenden Felder nach
oben und galten als falsch. Deshalb schnitt T4 bisher bei *allen* Modellen schlecht ab;
gemma4:12b hatte T4 in Wahrheit schon vorher weitgehend richtig.

| Modell | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | T9 | Summe | Pct |
|--------|----|----|----|----|----|----|----|----|----|-------|-----|
| **gemma4:12b** | +8 | +8 | +8 | +8 | +8 | +8 | +8 | +8 | +8 | 69.5/72 | **97%** |
| qwen3:14b | +8 | ~6 | +8 | -4 | +8 | +8 | +8 | +7 | +7 | 64.0/72 | 89% |
| qwen3:8b | +8 | +8 | +8 | -4 | +8 | ~6 | +8 | ~5 | +8 | 61.5/72 | 85% |
| gemma4:e2b | +8 | ~6 | ~6 | -3 | +8 | +8 | +8 | ~6 | +7 | 59.5/72 | 83% |
| deepseek-r1:14b | +8 | -1 | ~6 | -4 | +8 | -3 | -2 | -1 | ~6 | 39.0/72 | 54% |

Zum Vergleich mit altem Prompt und korrigierter Bewertung: gemma4:12b 95%, qwen3:8b 90%,
qwen3:14b 86%. Der Rueckgang bei qwen3:8b kommt aus T6 (schreibt "Gynäkologie" mit Umlaut,
der Test erwartet "Gynaekologie" – kein echter Fehler) und T8.

### T4: qwen3 erfindet Daten – unabhaengig von Prompt und Temperatur

T4 ist ein Brief ohne Vorname, Geburtsdatum und Briefdatum. Getestet mit Temperatur 0.0, 0.1,
0.4 und 0.7, je zwei Laeufe:

- **qwen3:8b** liefert bei jeder Temperatur "Klaus / 01.01.1980 / 20.01.2026". "Klaus" ist der
  Vorname des Absenders, die beiden Daten stammen aus den Beispielen im Prompt. Ein
  ausdrueckliches Verbot ("uebernimm NIEMALS Daten aus den Beispielen") aendert nichts.
- **qwen3:14b** erfindet Daten, bei hoeherer Temperatur jedes Mal andere (15.04.1968,
  12.04.1965, ...) – eindeutig geraten.
- **gemma4:12b** laesst alle drei Felder leer.

Warum das zum Ausschluss fuehrt: Medidok ordnet den Brief ueber Name und Geburtsdatum dem
Patienten zu. Ein erfundenes Geburtsdatum landet beim falschen Patienten. Das betrifft nicht
nur Briefe ohne Geburtsdatum, sondern auch jeden Scan, auf dem die OCR das Datum nicht lesen
kann (wie das Briefdatum in Brief B).

---

## Vorherige Testrunde (20.09.2026)

Die T4-Werte dieser Runde sind durch den oben beschriebenen Bewertungsfehler zu niedrig.

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

## Testergebnisse 20.09.2026 (alter Prompt, alte Bewertung)

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
    "gemma4:12b",   # echte Briefe 100%, T1-T9 97%, laesst fehlende Daten leer
]
```

Entfernt am 24.09.2026 (siehe Testrunde oben):
- **qwen3:8b, qwen3:14b** – erfinden fehlende Geburts- und Briefdaten (T4), unabhaengig von
  Prompt und Temperatur
- **gemma4:e2b** – vertauscht Namen sowie Empfaenger/Absender, laesst Zeilen aus

Frueher entfernt:
- **deepseek-r1:14b** (61%, unzuverlaessig bei laengerem Reasoning, siehe oben)
- **qwen2.5:7b, qwen2.5:14b, gpt-oss:20b** (von einem qwen3-Modell gleicher/kleinerer
  Groessenklasse klar geschlagen, siehe "Aeltere Testrunden")
- **gemma4:26b** (Totalausfall ueber `/api/generate`, siehe "Aeltere Testrunden"; am
  24.09.2026 nachgetestet und nicht aufgenommen, siehe Empfehlungen)

---

## Empfehlungen fuer den Produktionsbetrieb

### Standard-Modell: gemma4:12b
Einziges getestetes Modell, das bei fehlenden Angaben nichts erfindet, und fehlerfrei auf den
drei echten Briefen. Mit ~1-2 s pro Brief schnell genug; braucht 7.6 GB VRAM (qwen3:8b: 5.2 GB).

### gemma4:26b: nachgetestet, nicht aufgenommen (24.09.2026)
Seit dem `/api/chat`-Fix liefert es Antworten: echte Briefe 98% (einmal ein abgeschnittener Klinikname -
die Antworten schwanken zwischen Laeufen), T1-T9 91%. Bei T4 schreibt es
Platzhalter "01.01.1900 / 01.01.2000" statt leerer Zeilen, der erste Aufruf dauert ~13 s, und
es belegt 18 GB statt 7.6 GB. In keinem Punkt besser als gemma4:12b.

### Datumspruefung im Backend (umgesetzt 24.09.2026)
`_drop_invented_dates()` in `services/summarizer.py` leert Geburts- und Briefdatum, wenn das
Datum nicht in dem Text steht, den das LLM bekommen hat (erkennt auch "6.1.80" und
"8. Maerz 2025"). Geprueft: alle korrekten Daten aus T1-T9 und den drei echten Briefen
bleiben erhalten; die beobachteten erfundenen Daten von qwen3 und gemma4:26b werden geleert.
Ein leeres Feld erscheint im Import als "Unbekannt" und faellt in der Kontrolle auf.
Kehrseite: Hat das LLM ein von der OCR verstuemmeltes Datum richtig "repariert", wird es
ebenfalls geleert.

### Umlaut-Encoding (T8)
PyMuPDF liest die Textebene von `Test2.pdf` mit korrekten Umlauten. Da digitale Seiten jetzt
nicht mehr durch OCR laufen, kommt dieser Text unveraendert beim LLM an. Das kaputte Encoding
im Testfall T8 bleibt als Belastungsprobe erhalten.

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
MODEL_LLM1 = "gemma4:12b"   # Standard, erfindet keine fehlenden Daten, ~7.6 GB VRAM
DEFAULT_TEMPERATURE = 0.0
```

---

*Tests durchgefuehrt: 16.05.2026 (7 Testfaelle), 20.09.2026 (9 Testfaelle inkl. 2 echter
Arztbriefe) und 24.09.2026 (3 echte Briefe durch die komplette Kette, T1-T9 neu bewertet)*
*Testskripte: `test_qualitaet.py` (synthetisch, vom Host) und `test_echte_briefe.py` (echte
Briefe, im Container)*
