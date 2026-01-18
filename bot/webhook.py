from fastapi import APIRouter, Request, HTTPException
from telegram import Update
from telegram.ext import Application
from bot.config import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Global bot application instance
bot_app = None

@router.post("/webhook")
async def webhook_handler(request: Request):
    """Handle incoming Telegram webhook updates"""
    if not bot_app:
        raise HTTPException(status_code=500, detail="Bot not initialized")

    try:
        # Verify secret token if configured
        if settings.SECRET_TOKEN:
            token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if token != settings.SECRET_TOKEN:
                raise HTTPException(status_code=403, detail="Invalid secret token")

        # Process update
        update = Update.de_json(await request.json(), bot_app.bot)
        await bot_app.process_update(update)
        return {"status": "ok"}

    except Exception as e:
        logger.exception(f"Webhook processing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

async def setup_webhook():
    """Register webhook with Telegram"""
    if not settings.WEBHOOK_URL:
        logger.info("No WEBHOOK_URL configured, using polling mode")
        return False

    try:
        from telegram.ext import ApplicationBuilder
        app = ApplicationBuilder().token(settings.BOT_TOKEN).build()

        # Set webhook
        webhook_url = f"{settings.WEBHOOK_URL}/webhook"
        if settings.SECRET_TOKEN:
            await app.bot.set_webhook(
                url=webhook_url,
                secret_token=settings.SECRET_TOKEN
            )
        else:
            await app.bot.set_webhook(url=webhook_url)

        logger.info(f"Webhook registered at {webhook_url}")
        return True

    except Exception as e:
        logger.error(f"Failed to register webhook: {e}")
        return False
