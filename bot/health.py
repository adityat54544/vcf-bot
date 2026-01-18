from fastapi import APIRouter, Response
from bot.config import settings
import logging

# Import telegram_app lazily to avoid circular import
telegram_app = None

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health")
async def health_check():
    """Health check endpoint for liveness/readiness probes"""
    try:
        # Basic health check - always returns OK if FastAPI is running
        health_status = {
            "status": "ok",
            "service": "aura-vcf-bot",
            "version": "1.0.0"
        }

        # Add Telegram bot status information
        if telegram_app is None:
            health_status["telegram_bot"] = {
                "status": "not_initialized",
                "reason": "Telegram bot initialization failed or timed out"
            }
        else:
            health_status["telegram_bot"] = {
                "status": "initialized",
                "message": "Telegram bot is ready"
            }

        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "reason": str(e)
        }
