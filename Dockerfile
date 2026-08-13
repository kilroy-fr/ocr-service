FROM python:3.12-slim

# Deutsche Locales und UTF-8 Support
ENV LANG=de_DE.UTF-8
ENV LC_ALL=de_DE.UTF-8
ENV LANGUAGE=de_DE:de
ENV PYTHONIOENCODING=utf-8

# System-Pakete installieren
RUN apt-get update && \
    apt-get install -y \
        ocrmypdf \
        tesseract-ocr \
        tesseract-ocr-deu \
        ghostscript \
        locales && \
    # Deutsche Locales generieren
    echo "de_DE.UTF-8 UTF-8" >> /etc/locale.gen && \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen de_DE.UTF-8 && \
    update-locale LANG=de_DE.UTF-8 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements kopieren und installieren
COPY requirements.txt .

# --only-binary: Es gibt keinen Compiler im Image. Sollte ein Paket kuenftig
# kein passendes Wheel mehr liefern, bricht der Build hier klar ab, statt
# undurchsichtig an einem fehlenden gcc zu scheitern.
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# Anwendung kopieren
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]