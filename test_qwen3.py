#!/usr/bin/env python3
"""Test-Script für qwen3:14b mit verschiedenen Parametern"""
import requests
import time

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"

test_prompt = """Du bist eine Assistenz-KI für medizinische Dokumentenanalyse. Deine Aufgabe ist es, strukturierte Daten zu extrahieren.

KRITISCHE REGEL: Gib EXAKT sieben Zeilen zurück. Niemals mehr, niemals weniger.

Testdokument:
Name: Müller
Vorname: Hans
Geburtsdatum: 15.03.1965
Datum: 12.01.2025
Arzt: Dr. Schmidt
Befund: Routine-Untersuchung ohne Befund
Kategorie: 5 (Praxis)

Bitte extrahiere die 7 Informationen."""

def test_model(model_name, options, timeout=60):
    """Testet ein Modell mit gegebenen Optionen"""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print(f"Options: {options}")
    print(f"Timeout: {timeout}s")
    print('='*60)

    payload = {
        'model': model_name,
        'prompt': test_prompt,
        'stream': False,
        'options': options
    }

    start = time.time()
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        elapsed = time.time() - start

        if response.ok:
            result = response.json().get('response', '').strip()
            lines = result.split('\n')

            print(f"✅ SUCCESS ({elapsed:.1f}s)")
            print(f"Lines returned: {len(lines)}")
            print(f"Response:\n{result}")

            return True, elapsed, result
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False, elapsed, None

    except requests.Timeout:
        elapsed = time.time() - start
        print(f"⏱️ TIMEOUT after {elapsed:.1f}s")
        return False, elapsed, None

    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ ERROR: {e}")
        return False, elapsed, None


# Test 1: qwen3:14b mit Standard-Parametern
print("\n" + "="*60)
print("TEST 1: qwen3:14b mit Standard-Parametern")
print("="*60)
test_model("qwen3:14b", {
    'temperature': 0.0,
    'top_p': 0.9,
    'top_k': 10,
    'repeat_penalty': 1.1,
    'num_predict': 200,
    'stop': ['\n\n\n']
}, timeout=30)

# Test 2: qwen3:14b mit NEUEN optimierten Parametern
print("\n" + "="*60)
print("TEST 2: qwen3:14b mit NEUEN optimierten Parametern (weniger restriktiv)")
print("="*60)
test_model("qwen3:14b", {
    'temperature': 0.1,
    'top_p': 0.95,
    'top_k': 40,
    'repeat_penalty': 1.05,
    'num_predict': 300,
    'num_ctx': 2048
    # KEINE stop-tokens!
}, timeout=60)

# Test 3: qwen2.5:14b zum Vergleich
print("\n" + "="*60)
print("TEST 3: qwen2.5:14b zum Vergleich")
print("="*60)
test_model("qwen2.5:14b", {
    'temperature': 0.0,
    'top_p': 0.9,
    'top_k': 10,
    'repeat_penalty': 1.1,
    'num_predict': 200,
    'stop': ['\n\n\n']
}, timeout=30)

# Test 4: deepseek-r1:14b mit optimierten Parametern
print("\n" + "="*60)
print("TEST 4: deepseek-r1:14b mit optimierten Parametern")
print("="*60)
test_model("deepseek-r1:14b", {
    'temperature': 0.1,
    'top_p': 0.95,
    'top_k': 40,
    'repeat_penalty': 1.05,
    'num_predict': 400,
    'num_ctx': 2048
}, timeout=60)

# Test 5: gpt-oss:20b mit optimierten Parametern
print("\n" + "="*60)
print("TEST 5: gpt-oss:20b mit optimierten Parametern")
print("="*60)
test_model("gpt-oss:20b", {
    'temperature': 0.2,
    'top_p': 0.95,
    'top_k': 50,
    'repeat_penalty': 1.05,
    'num_predict': 400,
    'num_ctx': 2048
}, timeout=90)

print("\n" + "="*60)
print("Tests abgeschlossen!")
print("="*60)
