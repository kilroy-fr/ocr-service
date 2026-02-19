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
        libjpeg-dev \
        zlib1g-dev \
        locales \
        gcc \
        python3-dev && \
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

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Anwendung kopieren
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]