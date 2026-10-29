FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for C compilation (Tree-sitter) and Git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pre-install CPU-only PyTorch (avoids 2.5GB of CUDA packages and prevents Render 512MB OOM)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy requirements and install remaining dependencies
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code so both `backend.app...` and `app...` import paths resolve
COPY . /app/backend/
RUN cp -r /app/backend/app /app/app

ENV PYTHONPATH=/app:/app/backend
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
