import logging
import queue
import sys
import os
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener
from config import LOGGING_FOLDER

# Thread-sichere Queue für Log-Messages
log_queue = queue.Queue()
ui_log_queue = queue.Queue()  # separat

# Formatter mit Zeitstempel
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S")

# Verzeichnis sicherstellen
log_dir = LOGGING_FOLDER
os.makedirs(log_dir, exist_ok=True)

# Dateipfad zusammensetzen
log_file_path = os.path.join(log_dir, "ocr-app.log")

# File-Handler mit dynamischem Pfad
file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
file_handler.setFormatter(formatter)

# Optional: zusätzlich zur Konsole loggen
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Root Logger vorbereiten
logger = logging.getLogger("ocr-app")
logger.setLevel(logging.INFO)  # Oder DEBUG für mehr Details
logger.propagate = False  # Verhindert doppelte Ausgaben

# QueueHandler sorgt für Thread-Sicherheit
queue_handler = QueueHandler(log_queue)
logger.addHandler(queue_handler)

# Listener verarbeitet Queue-Inhalte
listener = QueueListener(log_queue, file_handler, console_handler)
listener.start()

# Shortcut-Funktion
def log(message, level="info"):
    log_record = logger.makeRecord(
        name=logger.name,
        level=getattr(logging, level.upper(), logging.INFO),
        fn='',
        lno=0,
        msg=message,
        args=None,
        exc_info=None
    )
    
    formatted_message = formatter.format(log_record)
    ui_log_queue.put(formatted_message)  # jetzt mit Formatierung wie File/Konsole
    
    # Nun tatsächliches Logging ausführen
    logger.handle(log_record)

