FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download en_core_web_sm

COPY . .

RUN useradd --create-home --shell /bin/bash raksh && \
    chown -R raksh:raksh /app

USER raksh

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

EXPOSE 10000

CMD uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
