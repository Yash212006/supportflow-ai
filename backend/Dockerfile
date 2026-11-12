FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.lock.txt ./
COPY vendor ./vendor
RUN pip install -r requirements.lock.txt

COPY . .
RUN useradd --create-home --uid 10001 app && mkdir -p /app/uploads && chown -R app /app/uploads
USER app

EXPOSE 8000
# start.sh: apply migrations, then serve. Seeding is a separate step (docker-compose `seed`), or SEED_ON_START=true on hosts without a shell.
CMD ["sh", "start.sh"]
