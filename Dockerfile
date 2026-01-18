FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Install system dependencies (as root)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies (as root)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and make scripts executable (as root)
COPY . .
RUN chmod +x scripts/start.sh

# Create and switch to non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=15s --timeout=5s \
    CMD curl -f http://localhost:$PORT/health || exit 1

EXPOSE $PORT

CMD ["./scripts/start.sh"]
