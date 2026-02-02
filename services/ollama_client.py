import requests
from config import MODEL_LLM1, OLLAMA_URL
from flask import session
from .logger import log


def check_ollama_health():
    """
    Prüft, ob Ollama erreichbar ist.

    Returns:
        tuple: (bool, str) - (Erfolg, Fehlermeldung falls nicht erreichbar)
    """
    try:
        # Versuche das Tags-Endpoint zu erreichen (leichtgewichtig)
        tags_url = OLLAMA_URL.replace('/api/generate', '/api/tags')
        response = requests.get(tags_url, timeout=5)

        if response.ok:
            log("✅ Ollama Health-Check erfolgreich")
            return True, None
        else:
            msg = f"Ollama ist nicht erreichbar (HTTP {response.status_code})"
            log(f"❌ {msg}", level="error")
            return False, msg
    except requests.exceptions.Timeout:
        msg = "Ollama ist nicht erreichbar (Timeout nach 5 Sekunden)"
        log(f"❌ {msg}", level="error")
        return False, msg
    except requests.exceptions.ConnectionError:
        msg = "Ollama ist nicht erreichbar (Verbindung fehlgeschlagen). Bitte starten Sie Ollama: 'docker-compose up ollama -d'"
        log(f"❌ {msg}", level="error")
        return False, msg
    except Exception as e:
        msg = f"Ollama Health-Check fehlgeschlagen: {str(e)}"
        log(f"❌ {msg}", level="error")
        return False, msg


def warmup_ollama():
    dummy_prompt = "Dies ist ein Dummy-Text zur Initialisierung. Bitte ignoriere diesen Text."
    
    # Versuche Modell aus Session zu holen, sonst Fallback
    try:
        selected_model = session.get("selected_model", MODEL_LLM1)
    except RuntimeError:
        # Außerhalb Request-Context
        selected_model = MODEL_LLM1
    
    log(f"Ollama wird vorgewärmt mit Modell: {selected_model}")
    try:
        response = requests.post(
            OLLAMA_URL,
            json={'model': selected_model, 'prompt': dummy_prompt, 'stream': False},
            timeout=15
        )
        log("Ollama erfolgreich gewärmt." if response.ok else f"Ollama Warm-up fehlgeschlagen: {response.status_code}")
    except Exception as e:
        log(f"Ollama nicht erreichbar: {e}")


def send_to_ollama(prompt, mnr, model, temperature=None):
    """
    Sendet einen Prompt an Ollama mit optimierten Parametern für strukturierte Datenextraktion.

    Args:
        prompt: Der zu verarbeitende Text-Prompt
        mnr: Referenz-Nummer für Logging (wird derzeit nicht verwendet)
        model: LLM-Modell (z.B. "qwen2.5:14b") - PFLICHTPARAMETER
        temperature: Optional - Überschreibt Session-Default (empfohlen: 0.0 für Extraktion)

    Returns:
        str: Response vom LLM oder None bei Fehler
    """
    # Temperature aus Session holen, falls nicht explizit übergeben
    if temperature is None:
        try:
            temperature = session.get("temperature", 0.0)
        except RuntimeError:
            # Außerhalb Request-Context
            temperature = 0.0

    # Modell-spezifische Optimierungen
    is_qwen3_14b = model.startswith("qwen3:14b")
    is_deepseek_r1 = model.startswith("deepseek-r1")
    is_gpt_oss = model.startswith("gpt-oss")

    # Qwen3:14b braucht spezielle Parameter (weniger restriktiv als qwen2.5)
    if is_qwen3_14b:
        options = {
            'temperature': 0.1,             # Minimal höher als 0, sonst zu restriktiv
            'top_p': 0.95,                  # Weniger streng, mehr Flexibilität
            'top_k': 40,                    # Mehr Tokens für bessere Auswahl
            'repeat_penalty': 1.05,         # Schwächer, qwen3 braucht Wiederholungen für Format
            'num_predict': 400,             # Genug Tokens für 7 vollständige Zeilen
            'num_ctx': 2048,                # Erhöhter Kontext für besseres Verständnis
            # KEINE stop-tokens! qwen3 stoppt sonst zu früh
        }
        timeout = 60  # Längerer Timeout

    elif is_deepseek_r1:
        # DeepSeek-R1 braucht ähnliche Parameter wie qwen3
        options = {
            'temperature': 0.1,
            'top_p': 0.95,
            'top_k': 40,
            'repeat_penalty': 1.05,
            'num_predict': 400,
            'num_ctx': 2048,
        }
        timeout = 60

    elif is_gpt_oss:
        # GPT-OSS ist sehr groß und langsam - braucht mehr Zeit und weniger Restriktionen
        options = {
            'temperature': 0.2,             # Etwas höher für Kreativität
            'top_p': 0.95,
            'top_k': 50,
            'repeat_penalty': 1.05,
            'num_predict': 400,
            'num_ctx': 2048,
        }
        timeout = 90  # Sehr langer Timeout wegen Modellgröße

    else:
        # Standard-Parameter für andere Modelle (qwen2.5:14b, qwen3:8b, etc.)
        options = {
            'temperature': temperature,      # 0.0 = deterministisch, konsistent
            'top_p': 0.9,                   # Reduziert Kreativität, fokussiert auf wahrscheinlichste Tokens
            'top_k': 10,                    # Begrenzt Token-Auswahl auf Top-10
            'repeat_penalty': 1.1,          # Verhindert Wiederholungen
            'num_predict': 200,             # Max. Tokens (~7 Zeilen à 25-30 Tokens)
            'stop': ['\n\n\n'],            # Stoppt bei 3 aufeinanderfolgenden Leerzeilen
        }
        timeout = 30

    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'options': options
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=timeout
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        log(f"Fehler bei der Anfrage an Ollama: {e}")
        if response := locals().get("response"):
            log(f"Antwort von Ollama: {response.text}")
        return None