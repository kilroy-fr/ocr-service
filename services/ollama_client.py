import requests
from config import MODEL_LLM1, MODEL_LLM2, OLLAMA_URL
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


def send_to_ollama(prompt, mnr, model):
    """
    Sendet einen Prompt an Ollama.
    
    Args:
        prompt: Der zu verarbeitende Text-Prompt
        mnr: Referenz-Nummer für Logging (wird derzeit nicht verwendet)
        model: LLM-Modell (z.B. "mistral-nemo:latest") - PFLICHTPARAMETER
        
    Returns:
        str: Response vom LLM oder None bei Fehler
    """
    try:
        response = requests.post(
            OLLAMA_URL,
            json={'model': model, 'prompt': prompt, 'stream': False},
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        log(f"Fehler bei der Anfrage an Ollama: {e}")
        if response := locals().get("response"):
            log(f"Antwort von Ollama: {response.text}")
        return None