#!/usr/bin/env python3
"""
Ersetzt alert() und confirm() Aufrufe durch Notifications API
"""
import re

def replace_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # alert() ersetzen - verschiedene Typen
    content = re.sub(r"alert\('Bitte", "Notifications.warning('Bitte", content)
    content = re.sub(r'alert\("Bitte', 'Notifications.warning("Bitte', content)
    content = re.sub(r"alert\('Keine", "Notifications.warning('Keine", content)
    content = re.sub(r'alert\("Keine', 'Notifications.warning("Keine', content)
    content = re.sub(r"alert\('Nur", "Notifications.warning('Nur", content)
    content = re.sub(r'alert\("Nur', 'Notifications.warning("Nur', content)
    content = re.sub(r"alert\('Fehler", "Notifications.error('Fehler", content)
    content = re.sub(r'alert\("Fehler', 'Notifications.error("Fehler', content)
    content = re.sub(r"alert\('Netzwerk", "Notifications.error('Netzwerk", content)
    content = re.sub(r'alert\("Netzwerk', 'Notifications.error("Netzwerk', content)
    content = re.sub(r"alert\(`✅", "Notifications.success(`", content)
    content = re.sub(r'alert\("✅', 'Notifications.success("', content)
    content = re.sub(r"alert\('✅", "Notifications.success('", content)

    # confirm() ersetzen - muss await haben
    content = re.sub(
        r'if \(!confirm\((`[^`]+`|"[^"]+"|\'[^\']+\')\)\)',
        r'if (!await Notifications.confirm(\1, "OK", "Abbrechen"))',
        content
    )
    content = re.sub(
        r'const proceed = confirm\((`[^`]+`|"[^"]+"|\'[^\']+\')\)',
        r'const proceed = await Notifications.confirm(\1, "OK", "Abbrechen")',
        content
    )

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ {filepath} aktualisiert")
        return True
    else:
        print(f"ℹ️ {filepath} - keine Änderungen")
        return False

if __name__ == "__main__":
    replace_file('static/app.js')
    replace_file('static/control.js')
