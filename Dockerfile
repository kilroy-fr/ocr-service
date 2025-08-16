FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y \
        ocrmypdf \
        tesseract-ocr \
        tesseract-ocr-deu \
        ghostscript \
        libjpeg-dev \
        zlib1g-dev && \
    apt-get clean

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
