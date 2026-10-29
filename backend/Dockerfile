FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for C compilation (Tree-sitter) and Git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Build context is the repo root (see docker-compose.yml) so the `backend`
# package keeps its name and `backend.app...` imports resolve.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

ENV PYTHONPATH=/app
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
