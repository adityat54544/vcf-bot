#!/bin/bash
set -e

# Validate environment
if [ -z "$BOT_TOKEN" ]; then
    echo "ERROR: BOT_TOKEN is required"
    exit 1
fi

# Railway.app automatically sets PORT, but we'll keep the default for compatibility
PORT=${PORT:-8000}

# Log Railway.app specific info if available
if [ -n "$RAILWAY_ENVIRONMENT" ]; then
    echo "Running on Railway.app environment: $RAILWAY_ENVIRONMENT"
fi

# Register webhook if configured
if [ -n "$WEBHOOK_URL" ]; then
    echo "Registering webhook..."
    python -c "
import os
from bot.webhook import setup_webhook
import asyncio

async def main():
    await setup_webhook()

asyncio.run(main())
"
fi

# Start the application
echo "Starting Aura VCF Bot on port $PORT..."
echo "Bot will be available at: http://0.0.0.0:$PORT"
exec gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT --workers 4 --timeout 120 bot.main:app
