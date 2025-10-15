# Medical OCR Service

Flask-basierter Dokumenten-Import-Service mit OCR und KI-gestützter Metadaten-Extraktion.

## Features

- ✅ OCR für medizinische Dokumente (Deutsch)
- 🤖 LLM-basierte Metadaten-Extraktion (Ollama)
- 📁 Staging-System für sichere Bearbeitung
- 🔄 Progressive Analyse großer Batches
- 🧩 PDF-Bearbeitung (Kombinieren, Splitten)

## Installation
```bash
# Repository klonen
git clone https://github.com/DEIN-USERNAME/medical-ocr-service.git
cd medical-ocr-service

# .env-Datei erstellen
cp .env.example .env
# .env mit echten Zugangsdaten bearbeiten

# Docker starten
docker-compose up -d
```

## Verwendung

Service läuft auf `http://localhost:5000`

## Technologie

- Python 3.10 + Flask
- OCRmyPDF + Tesseract
- Ollama (LLM)
- Docker + Docker Compose

