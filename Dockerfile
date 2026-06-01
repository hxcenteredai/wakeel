# =============================================================================
# Wakeel — Dockerfile
# =============================================================================
# Builds a single image that runs both the API (port 8000) and UI (port 8001).
# Usage:
#   docker build -t wakeel .
#   docker run -p 8000:8000 -p 8001:8001 --env-file .env wakeel
# =============================================================================

FROM python:3.11-slim AS base

# System deps (pypdf needs nothing extra; chromadb needs build tools on some bases)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure log/data dirs exist
RUN mkdir -p logs data/corpus/chromadb data/copilots

# Expose API and UI ports
EXPOSE 8000 8001

# Entrypoint: start API and UI together
# API runs in background, UI runs in foreground
# (For production we'd use supervisord or split containers; this is fine for v1.)
CMD ["sh", "-c", "python run.py & streamlit run run_ui.py --server.port 8001 --server.address 0.0.0.0 --server.headless true"]
