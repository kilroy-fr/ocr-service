#!/usr/bin/env python3
import requests, re, time

OLLAMA_URL = "http://localhost:11434/api/generate"
PROMPT_TEMPLATE = open("prompt.txt", encoding="utf-8").read().strip()

FIELD_NAMES = ["Nachname","Vorname","Gebdat","Briefdat","Fachrichtg","Absender","Hauptbefund","Kategorie"]
EXPECTED_KEYS = ["nachname","vorname","geburtsdatum","briefdatum","fachrichtung","absender","hauptbefund_kw","kategorie"]

TEST_CASES = [
    {"id":1,"name":"Arztbrief standard","beschreibung":"Einfacher Facharztbrief",
     "text":"Gemeinschaftspraxis Dr. Schmidt\nKardiologie\nDatum: 15.01.2025\n\nPatient: Mueller, Hans\nGeburtsdatum: 12.03.1965\n\nDiagnose: Arterielle Hypertonie\nBefunde: Blutdruck 135/85 mmHg\nBeurteilung: Unter Ramipril 5mg gut eingestellt\n\nDr. med. Schmidt\nFacharzt fuer Kardiologie",
     "expected":{"nachname":"Mueller","vorname":"Hans","geburtsdatum":"12.03.1965","briefdatum":"15.01.2025","fachrichtung":"Kardiologie","absender":"Schmidt","hauptbefund_kw":["hypertonie","ramipril","blutdruck"],"kategorie":"5"}},
    {"id":2,"name":"Krankenhausentlassung","beschreibung":"Uniklinik Entlassbrief, Kategorie 6",
     "text":"Universitaetsklinikum Wuerzburg\nKlinik fuer Psychiatrie\nDirektor: Prof. Dr. Bauer\n\nEntlassungsbericht\n\nPatientin: Weber, Anna Christine\nGeburtsdatum: 22.05.1958\nAufnahme: 14.02.2025\nEntlassung: 03.03.2025\n\nDiagnose: Mittelgradige depressive Episode (F32.1)\nVerlauf: Stationaere Behandlung, gutes Ansprechen auf Antidepressiva.\nMedikation bei Entlassung: Sertralin 100mg, Mirtazapin 15mg\n\nProf. Dr. Bauer\nChefarzt Psychiatrie",
     "expected":{"nachname":"Weber","vorname":"Anna","geburtsdatum":"22.05.1958","briefdatum":"03.03.2025","fachrichtung":"Psychiatrie","absender":"Wuerzburg","hauptbefund_kw":["depressiv","sertralin","mirtazapin","f32"],"kategorie":"6"}},
    {"id":3,"name":"Laborbericht","beschreibung":"Laborwerte, Absender=Laborname",
     "text":"MVZ Labor Enders und Partner mbH\nBefundbericht vom 20.02.2025\n\nPatient: Schneider, Thomas\nGeburtsdatum: 14.07.1972\nEinsender: Dr. Hoffmann\n\nGOT (AST): 68 U/l Referenz < 50 ERHOET\nGPT (ALT): 112 U/l Referenz < 50 ERHOET\nGGT: 145 U/l Referenz < 60 ERHOET\n\nBeurteilung: Erhoehte Leberwerte, Kontrolle empfohlen.\n\nLabor Enders und Partner",
     "expected":{"nachname":"Schneider","vorname":"Thomas","geburtsdatum":"14.07.1972","briefdatum":"20.02.2025","fachrichtung":"Labor","absender":"Enders","hauptbefund_kw":["got","gpt","leber","erhoet"],"kategorie":"5"}},
    {"id":4,"name":"Fehlende Informationen","beschreibung":"Vorname, Gebdat, Briefdat fehlen",
     "text":"Orthopaedie am Markt\nDr. med. Klaus Bauer, Facharzt fuer Orthopaedie\n\nSehr geehrte Kollegin, sehr geehrter Kollege,\n\nIch berichte ueber Ihren Patienten Herrn Hoffmann.\n\nDiagnose: Lumboischialgie links, chronisch rezidivierend\nTherapie: Physiotherapie und NSAR-Behandlung.\nVerlauf: Beschwerdebesserung unter Therapie.\n\nMit freundlichen Gruessen\nDr. med. Klaus Bauer",
     "expected":{"nachname":"Hoffmann","vorname":"","geburtsdatum":"","briefdatum":"","fachrichtung":"Orthopaedie","absender":"Bauer","hauptbefund_kw":["lumbo","physiotherapie","nsar"],"kategorie":"5"}},
    {"id":5,"name":"Komplexer Absendername","beschreibung":"Akadem. Titel + Doppelname, nur Kernname erwartet",
     "text":"Neurologische Fachpraxis\nProf. Dr. med. habil. Mueller-Berger, MHBA\nZertifiziertes Parkinson-Zentrum\n\nBefundbericht vom 12.04.2025\n\nPatientin: Fischer, Elisabeth Maria\nGeburtsdatum: 03.09.1948\n\nDiagnose: Idiopathisches Parkinson-Syndrom (G20), Stadium III\nVerlauf: Langsame Progredienz, Tremor-Dominanz links.\nMedikation: L-Dopa/Carbidopa 100/25mg 3x tgl., Ropinirol 2mg retard.\n\nProf. Dr. med. habil. Mueller-Berger, MHBA",
     "expected":{"nachname":"Fischer","vorname":"Elisabeth","geburtsdatum":"03.09.1948","briefdatum":"12.04.2025","fachrichtung":"Neurologie","absender":"Mueller-Berger","hauptbefund_kw":["parkinson","tremor","l-dopa","ropinirol"],"kategorie":"5"}},
    {"id":6,"name":"Adeliger Doppelname","beschreibung":"von der Heyden, korrekte Zerlegung",
     "text":"Frauenaerztliche Gemeinschaftspraxis\nDr. med. Zimmermann und Dr. med. Krause\nGynaekologie und Geburtshilfe\n\nAerztlicher Brief vom 28.01.2025\n\nPatientin: von der Heyden, Maria-Luise\nGeburtsdatum: 18.11.1961\n\nBefund: Routineuntersuchung, Mammographie unauffaellig.\nZervixabstrich: negativ (Pap I).\nEmpfehlung: Naechste Vorsorge in 12 Monaten.\n\nDr. med. Zimmermann",
     "expected":{"nachname":"Heyden","vorname":"Maria-Luise","geburtsdatum":"18.11.1961","briefdatum":"28.01.2025","fachrichtung":"Gynaekologie","absender":"Zimmermann","hauptbefund_kw":["routine","mammographie","pap","zervix"],"kategorie":"5"}},
    {"id":7,"name":"Ausgeschr. Datum und 2 Aerzte","beschreibung":"Datum als Langtext, zwei Unterzeichner",
     "text":"Urologische Praxisgemeinschaft\nDr. med. Andreas Braun und Dr. med. Petra Schwarz\nFachgebiet: Urologie\n\nMuenchen, den 8. Maerz 2025\n\nPatient: Klein, Robert Hermann\nGeburtsdatum: 25.06.1955\n\nBefundbericht:\nPSA-Wert: 6.8 ng/ml (Normalwert < 4.0) maessig erhoet\nProstatavolumen: 45 ml\nEmpfehlung: Biopsie zur Abklaerung empfohlen.\n\nDr. med. Braun   Dr. med. Schwarz",
     "expected":{"nachname":"Klein","vorname":"Robert","geburtsdatum":"25.06.1955","briefdatum":"08.03.2025","fachrichtung":"Urologie","absender":"Braun","hauptbefund_kw":["psa","prostata","biopsie","erhoet"],"kategorie":"5"}},
]

ALLOWED_MODELS = [
    "qwen2.5:7b", "qwen3:8b", "gemma4:e2b", "deepseek-r1:14b",
    "qwen2.5:14b", "qwen3:14b", "gpt-oss:20b", "gemma4:26b",
]

def send_to_ollama(prompt, model):
    is_qwen3 = model.startswith("qwen3:")
    is_deepseek_r1 = model.startswith("deepseek-r1")
    is_gpt_oss = model.startswith("gpt-oss")
    is_gemma4 = model.startswith("gemma4:")
    if is_qwen3:
        options = {"temperature":0.1,"top_p":0.95,"top_k":40,"repeat_penalty":1.05,"num_predict":400,"num_ctx":2048}
        timeout = 60
    elif is_deepseek_r1:
        options = {"temperature":0.1,"top_p":0.95,"top_k":40,"repeat_penalty":1.05,"num_predict":400,"num_ctx":2048}
        timeout = 60
    elif is_gpt_oss:
        options = {"temperature":0.2,"top_p":0.95,"top_k":50,"repeat_penalty":1.05,"num_predict":2000,"num_ctx":4096}
        timeout = 120
    elif is_gemma4:
        options = {"temperature":0.1,"top_p":0.95,"top_k":40,"repeat_penalty":1.05,"num_predict":2000,"num_ctx":4096}
        timeout = 120
    else:
        options = {"temperature":0.0,"top_p":0.9,"top_k":10,"repeat_penalty":1.1,"num_predict":200,"stop":["\n\n\n"]}
        timeout = 30
    payload = {"model":model,"prompt":prompt,"stream":False,"options":options,
               **({"think":False} if is_qwen3 or is_deepseek_r1 else {})}
    t0 = time.time()
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        r.raise_for_status()
        elapsed = round(time.time()-t0, 1)
        raw = r.json().get("response","").strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        return raw, elapsed
    except Exception:
        return None, round(time.time()-t0, 1)

def score_field(idx, got, expected):
    if idx == 6:
        kws = expected.get("hauptbefund_kw", [])
        hits = sum(1 for kw in kws if kw in got.lower())
        if hits >= 2:   return 1.0, f"{hits}/{len(kws)} KW"
        elif hits == 1: return 0.5, f"1/{len(kws)} KW"
        else:           return 0.0, f"0 KW: {got[:30]}"
    exp_val = expected.get(EXPECTED_KEYS[idx], "")
    if exp_val == "":
        if not got or got.lower() in ("","unbekannt","-","n/a","keine angabe","nicht angegeben"):
            return 1.0, "leer OK"
        return 0.0, f"soll leer, hat: {got[:25]}"
    if exp_val.lower() in got.lower():
        return 1.0, "OK"
    parts = exp_val.lower().split("-")
    if any(p in got.lower() for p in parts if len(p) > 2):
        return 0.5, f"teilweise: {got[:25]}"
    return 0.0, f"erwartet '{exp_val}' | got '{got[:25]}'"

def evaluate(raw, expected):
    if not raw:
        return [(0.0,"keine Antwort","")] * 8
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    while len(lines) < 8:
        lines.append("")
    return [(*score_field(i, lines[i], expected), lines[i]) for i in range(8)]

print("=" * 80)
print("QUALITAETSTEST: Inhaltliche Guete der LLM-Datenextraktion")
print(f"Datum: {time.strftime('%d.%m.%Y')} | {len(TEST_CASES)} Testdokumente | {len(ALLOWED_MODELS)} Modelle")
print("=" * 80)

all_results = {m: {} for m in ALLOWED_MODELS}
MAX_SCORE = 8.0

for model in ALLOWED_MODELS:
    print(f"\n{'-'*80}\n  Modell: {model}\n{'-'*80}")
    model_total = 0.0
    for tc in TEST_CASES:
        full_prompt = f"{PROMPT_TEMPLATE}\n\n{tc['text']}"
        raw, elapsed = send_to_ollama(full_prompt, model)
        fscores = evaluate(raw, tc["expected"])
        tc_score = sum(s for s,_,_ in fscores)
        model_total += tc_score
        all_results[model][tc["id"]] = (tc_score, fscores, elapsed, raw)
        sym = "GUT " if tc_score >= 7 else ("MITT" if tc_score >= 5 else "SCHL")
        print(f"  [{sym}] T{tc['id']}: {tc['name']:<38} {tc_score:.1f}/8  ({elapsed}s)")
        for i,(s,note,_) in enumerate(fscores):
            if s < 1.0:
                print(f"         Feld {i+1} {FIELD_NAMES[i]:<11}: {note}")
    pct = model_total / (MAX_SCORE*len(TEST_CASES)) * 100
    print(f"  => Gesamt: {model_total:.1f}/{MAX_SCORE*len(TEST_CASES):.0f} ({pct:.0f}%)")

print("\n" + "="*80 + "\nGESAMTERGEBNIS\n" + "="*80)
possible = MAX_SCORE * len(TEST_CASES)
hdr = f"{'Modell':<20}" + "".join(f"  T{tc['id']}" for tc in TEST_CASES) + f"  {'Summe':>9}  Pct"
print(hdr)
print("-"*len(hdr))
ranking = []
for model in ALLOWED_MODELS:
    row = f"{model:<20}"
    total = 0.0
    for tc in TEST_CASES:
        s,_,_,_ = all_results[model][tc["id"]]
        total += s
        sym = "+" if s>=7 else ("~" if s>=5 else "-")
        row += f"  {sym}{s:.0f}"
    pct = total/possible*100
    row += f"  {total:>5.1f}/{possible:.0f}  {pct:>3.0f}%"
    ranking.append((pct, model))
    print(row)
print("\nLegende: +  = gut (>=7/8)   ~  = mittel (5-6/8)   -  = schlecht (<5/8)")
print("\n" + "="*80 + "\nRANKING\n" + "="*80)
for rank,(pct,model) in enumerate(sorted(ranking,reverse=True),1):
    print(f"  {rank}. {model:<20} {pct:.0f}%")

