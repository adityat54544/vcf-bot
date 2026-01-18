import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    BOT_TOKEN: str = "7644164685:AAG1b0fmrR-iOS6j5q535YK34P42722s6cY"  # Hardcoded bot token
    WEBHOOK_URL: str = ""
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    SECRET_TOKEN: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()
