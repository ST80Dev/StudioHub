FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Utente non-root per l'app
RUN useradd --system --uid 1001 --gid 0 --create-home --home-dir /home/app app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=app:0 requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:0 . .

# Cartelle scrivibili dall'app
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R app:0 /app/staticfiles /app/media

USER app

EXPOSE 8000

CMD ["gunicorn", "studiohub.wsgi:application", "--bind", "0.0.0.0:8000"]
