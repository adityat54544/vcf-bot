import os
import logging
from fastapi import FastAPI
from telegram.ext import ApplicationBuilder
from bot.config import settings
from bot.health import router as health_router
from bot.webhook import router as webhook_router, setup_webhook, bot_app
from bot.telegram_bot import setup_handlers

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Aura VCF Bot API",
    version="1.0.0",
    description="Telegram bot for VCF file manipulation"
)

# Include routers
app.include_router(health_router, prefix="", tags=["health"])
app.include_router(webhook_router, prefix="", tags=["webhook"])

# Global bot application
telegram_app = None

@app.on_event("startup")
async def startup():
    """Initialize bot on startup"""
    global telegram_app

    try:
        # Create Telegram application
        telegram_app = ApplicationBuilder().token(settings.BOT_TOKEN).build()
        bot_app = telegram_app  # Set global reference for webhook

        # Setup handlers
        setup_handlers(telegram_app)

        # Setup webhook or polling
        webhook_enabled = await setup_webhook()

        if not webhook_enabled:
            # Start polling if webhook not configured
            logger.info("Starting polling...")
            await telegram_app.initialize()
            await telegram_app.start()
            await telegram_app.updater.start_polling()

        logger.info("Bot started successfully")

    except Exception as e:
        logger.error(f"Startup failed: {e}")
        # Don't raise the exception - allow the FastAPI app to continue running
        # This ensures health checks will still work even if Telegram bot fails
        logger.warning("Telegram bot initialization failed, but FastAPI server will continue running")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()
