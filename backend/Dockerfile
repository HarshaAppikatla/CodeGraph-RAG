FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for C compilation (Tree-sitter) and Git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies with frozen constraints
COPY requirements.txt constraints.txt* ./
RUN if [ -f constraints.txt ]; then pip install --no-cache-dir -r requirements.txt -c constraints.txt; else pip install --no-cache-dir -r requirements.txt; fi

# Copy backend source code so both `backend.app...` and `app...` import paths resolve
COPY . /app/backend/
RUN cp -r /app/backend/app /app/app

ENV PYTHONPATH=/app:/app/backend
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --limit-concurrency 50"]
