FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies required by OCR and PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libtesseract-dev \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better Docker layer caching)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application source code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Copy supporting files needed at runtime
COPY sample_outputs/ ./sample_outputs/
COPY docs/ ./docs/

# Create directories the app expects at runtime
RUN mkdir -p /app/data /app/logs /app/uploads

# Default environment variables
# Render injects PORT automatically; TESSERACT_CMD left empty so it finds tesseract on PATH
ENV APP_ENV=production \
    LOG_LEVEL=INFO \
    DATABASE_URL=sqlite:///./data/app.db \
    TESSERACT_CMD="" \
    LLM_PROVIDER=gemini \
    PORT=8000

WORKDIR /app/backend

# Expose port (documentation only — Render overrides via $PORT)
EXPOSE 8000

# Start uvicorn, binding to 0.0.0.0 on the port Render provides via $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
