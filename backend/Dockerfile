FROM python:3.12-slim

# No .pyc files, and print logs immediately instead of buffering them.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /srv

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Do not run the app as root: a bug in the app then cannot change the container.
RUN useradd --system --no-create-home appuser
USER appuser

EXPOSE 8000

# Apply database migrations, then start the API. "exec" makes uvicorn the main
# process, so it receives the stop signal from Docker and shuts down cleanly.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
