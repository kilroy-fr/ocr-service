import requests
from config import MODEL_LLM1, OLLAMA_URL
from flask import session
from .logger import log

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

    # Optimierte Parameter für strukturierte Datenextraktion
    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'options': {
            'temperature': temperature,      # 0.0 = deterministisch, konsistent
            'top_p': 0.9,                   # Reduziert Kreativität, fokussiert auf wahrscheinlichste Tokens
            'top_k': 10,                    # Begrenzt Token-Auswahl auf Top-10
            'repeat_penalty': 1.1,          # Verhindert Wiederholungen
            'num_predict': 200,             # Max. Tokens (~7 Zeilen à 25-30 Tokens)
            'stop': ['\n\n\n'],            # Stoppt bei 3 aufeinanderfolgenden Leerzeilen
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
        if response := locals().get("response"):
            log(f"Antwort von Ollama: {response.text}")
        return None