#!/bin/bash
set -e

# Validate environment
if [ -z "$BOT_TOKEN" ]; then
    echo "ERROR: BOT_TOKEN is required"
    exit 1
fi

# Set default port if not provided
PORT=${PORT:-8000}

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
exec gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT --workers 4 bot.main:app
