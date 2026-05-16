# LLM Modell-Test: Qualitaetsergebnisse

**Letzte Aktualisierung:** 16.05.2026
**Test:** Strukturierte Datenextraktion aus medizinischen Dokumenten (8 Felder)

---

## Testaufbau

### Testdokumente (7 Szenarien)

| ID | Name | Schwerpunkt |
|----|------|-------------|
| T1 | Arztbrief standard | Basisfall, einfache Struktur |
| T2 | Krankenhausentlassung | Absender = Einrichtung, Kategorie 6 |
| T3 | Laborbericht | Absender = Laborname, Fachrichtung Labor |
| T4 | Fehlende Informationen | Vorname/Datum fehlen – keine Halluzination erwartet |
| T5 | Komplexer Absendername | Akadem. Titel + Doppelname, nur Kernname erwartet |
| T6 | Adeliger Doppelname | "von der Heyden, Maria-Luise" – korrekte Zerlegung |
| T7 | Ausgeschr. Datum + 2 Aerzte | "8. Maerz 2025", erster Unterzeichner erwartet |

### Scoring

- **Felder 1-4, 8** (Nachname, Vorname, Gebdat, Briefdat, Kategorie): exakter Substring-Match
- **Felder 5-6** (Fachrichtung, Absender): Substring-Match
- **Feld 7** (Hauptbefund): mindestens 2 von 4 definierten Keywords = 1 Punkt, 1 Keyword = 0.5 Punkte
- **Fehlende Felder**: 1 Punkt wenn leer/Unbekannt geliefert, 0 Punkte wenn Daten erfunden
- **Maximum:** 8 Punkte pro Testdokument, 56 Punkte gesamt

---

## Prompt-Versionen

### Prompt v1 (Original, vor 16.05.2026)

Absender-Regel: *"Bei Klinik/Krankenhaus: Kurzform (z.B. 'Uni Wuerzburg')"*
Fehlende-Felder-Regel: *"Leere Zeilen wenn Information fehlt. Immer 8 Zeilen."* (am Ende)

### Prompt v2 (16.05.2026, aktuelle Version)

Aenderungen gegenueber v1:
1. Absender-Regel praezisiert: *"Name der EINRICHTUNG, nicht der unterzeichnende Arzt"*
2. Fehlende-Felder-Regel prominenter platziert mit NIEMALS-Hinweis
3. Hauptbefund explizit als "ein Satz" definiert

---

## Testergebnisse

### Runde 1: Prompt v1 (Original)

| Modell | T1 | T2 | T3 | T4 | T5 | T6 | T7 | Summe | Pct |
|--------|----|----|----|----|----|----|-----|-------|-----|
| qwen3:8b | +8 | +8 | +8 | -4 | +8 | +8 | +8 | 50.5/56 | **90%** |
| qwen3:14b | +8 | ~6 | +8 | -4 | +8 | +8 | +8 | 49.5/56 | 88% |
| gemma4:e2b | +8 | ~6 | +8 | -1 | +8 | +8 | +8 | 46.0/56 | 82% |
| deepseek-r1:14b | +8 | +7 | +7 | -2 | +8 | +7 | +8 | 46.0/56 | 82% |
| qwen2.5:14b | +8 | ~6 | +8 | -3 | ~6 | +7 | +8 | 46.0/56 | 82% |
| gpt-oss:20b | +8 | -3 | +8 | -1 | +8 | +8 | +8 | 42.0/56 | 75% |
| qwen2.5:7b | ~6 | ~6 | ~6 | -4 | -4 | +8 | +8 | 41.5/56 | 74% |
| gemma4:26b | +8 | -0 | +8 | -0 | +8 | +8 | +8 | 38.0/56 | 68% |

### Runde 2: Prompt v2 (verbessert)

| Modell | T1 | T2 | T3 | T4 | T5 | T6 | T7 | Summe | Pct | Delta |
|--------|----|----|----|----|----|----|-----|-------|-----|-------|
| qwen3:8b | +8 | +8 | +8 | -4 | +8 | +8 | +8 | 48.5/56 | **87%** | -3% |
| qwen3:14b | +8 | +8 | +8 | -1 | +8 | +8 | +8 | 48.0/56 | 86% | -2% |
| gemma4:e2b | +8 | **+8** | +8 | -1 | +8 | +7 | +8 | 46.5/56 | 83% | +1% |
| deepseek-r1:14b | +8 | **+8** | +8 | -1 | +8 | +7 | -4 | 43.5/56 | 78% | -4% |
| qwen2.5:7b | +8 | ~6 | +8 | -1 | ~6 | +8 | +8 | 43.0/56 | 77% | +3% |
| gpt-oss:20b | +8 | -3 | +8 | -1 | ~6 | +8 | +8 | 41.5/56 | 74% | 0% |
| qwen2.5:14b | ~6 | ~5 | +8 | -1 | +7 | ~6 | +7 | 39.5/56 | 71% | **-11%** |
| gemma4:26b | +8 | -0 | -0 | -0 | +8 | -0 | -0 | 15.0/56 | **27%** | **-41%** |

Legende: + = gut (>=7/8) ~ = mittel (5-6/8) - = schlecht (<5/8) | Fett = auffaellige Veraenderung

---

## Schlussfolgerungen

### Strukturelle Schwachstellen (alle Modelle)

**T4 – Fehlende Informationen (universelles Problem)**
Alle Modelle erfinden Daten, wenn Felder fehlen, anstatt leere Zeilen zu liefern.
Der neue Prompt mit explizitem NIEMALS-Hinweis verbesserte T4 kaum.
Dies ist das groesste Qualitaetsrisiko im Produktionsbetrieb.

**T2 – Krankenhaus-Absender**
Prompt v2 verbesserte T2 bei gemma4:e2b und qwen3:14b auf 8/8.
Schwierigste Regel: Modelle tendieren dazu, den unterzeichnenden Arzt statt die Institution zu nennen.

### Modell-spezifische Erkenntnisse

**gemma4:26b – kritische Instabilitaet**
Mit dem laengeren Prompt v2 lieferte gemma4:26b bei 5 von 7 Testfaellen keine Antwort.
Reaktionszeiten ~77-84s deuten auf kein Timeout hin – das Modell gibt leere `response`-Felder zurueck.
Ursache: Vermutlich ueberschreitet Prompt + Dokumenttext die effektive Kontextlaenge des Modells.
**Empfehlung: Produktionseinsatz von gemma4:26b vermeiden.**

**qwen2.5:14b – Regression mit Prompt v2**
Rueckgang von 82% auf 71%, insbesondere bei T1 und T2 (Kategorie-Feld fehlt in der Ausgabe).
Das Modell scheint empfindlich auf Prompt-Aenderungen zu reagieren.

**qwen3:8b – konsistent bestes Modell**
Bester Gesamtscore in beiden Runden (90% / 87%).
Schnellste Inferenz (~3.5-4s pro Dokument).
Einzige Schwaeche: T4 (fehlende Informationen, wie alle anderen auch).

### Prompt-Aenderung: Bewertung

Die Einrichtungs-Praezisierung beim Absender (v2) war sinnvoll fuer T2.
Das "BEISPIEL FEHLENDE DATEN" wurde wieder entfernt – es verwirrt Modelle mehr als es hilft.
Aktueller Prompt (v2 ohne Fehlbeispiel) ist der beste Kompromiss.

---

## Aktuelles Ranking (Prompt v2, Stand 16.05.2026)

| Rang | Modell | Score | Staerken | Schwaechen |
|------|--------|-------|----------|------------|
| 1 | **qwen3:8b** | 87% | Schnell, konsistent, alle Strukturen | T4 Halluzination |
| 2 | **qwen3:14b** | 86% | T2+T6+T7 perfekt | T4 Halluzination |
| 3 | **gemma4:e2b** | 83% | T2 perfekt nach Prompt-Fix | T4 komplett falsch |
| 4 | deepseek-r1:14b | 78% | T2+T3 perfekt | T4+T7 Schwaechen |
| 5 | qwen2.5:7b | 77% | Zuverlaessig, schnell | T4+T5 schwach |
| 6 | gpt-oss:20b | 74% | T6+T7 perfekt | T2+T4 schlecht, langsam (20-30s) |
| 7 | qwen2.5:14b | 71% | T3+T7 gut | Prompt-sensitiv, T1+T2 variabel |
| 8 | gemma4:26b | 27% | T1+T5 gut | **5/7 Tests ohne Antwort** |

---

## Empfehlungen fuer den Produktionsbetrieb

### Standard-Modell: qwen2.5:14b (bewaehrt, deterministisch)
Trotz Rang 7 im Qualitaetstest bleibt qwen2.5:14b der empfohlene Standard:
- Temperature 0.0 = vollstaendig deterministisch (andere Modelle: 0.1)
- 9 GB VRAM, optimal fuer 16 GB VRAM Systeme
- Langjaehrig erprobt in der Produktion
- Der Qualitaetsrueckgang in Runde 2 koennte prompt-bedingt sein (naechster Test mit v1-Parametern noetig)

### Fuer hoehere Qualitaet: qwen3:8b
Falls Extraktionsqualitaet Vorrang hat: qwen3:8b liefert 87% bei unter 4 Sekunden.
Nur 5.2 GB VRAM – laeuft auch auf Systemen mit 8 GB.

### Nicht fuer Produktion: gemma4:26b
Zu instabil, zu langsam (40-80s), zu viele Leerantworten.

### Offenes Problem: T4 (fehlende Felder)
Kein Modell beherrscht zuverlaessig leere Zeilen bei fehlenden Informationen.
Empfehlung: Im Backend nach der LLM-Antwort prueefen, ob extrahierte Daten
plausibel sind (z.B. Geburtsdatum-Format, Datumsbereich).

---

## Konfiguration

```python
# config.py
MODEL_LLM1 = "qwen2.5:14b"   # Standard fuer 16 GB VRAM, Temperature 0.0
DEFAULT_TEMPERATURE = 0.0
```

---

*Tests durchgefuehrt: 16.05.2026 | Ollama via http://localhost:11434*
*Testskript: test_qualitaet.py (im Projektverzeichnis)*
