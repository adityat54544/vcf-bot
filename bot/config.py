import os

class Settings:
    BOT_TOKEN: str = "7644164685:AAG1b0fmrR-iOS6j5q535YK34P42722s6cY"  # Hardcoded bot token
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SECRET_TOKEN: str = os.getenv("SECRET_TOKEN", "")

settings = Settings()
