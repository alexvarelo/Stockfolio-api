from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Stockfolio Financial Data API"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # JWT Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10"))
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./stockfolio_api.db")
    
    # Supabase Configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SUPABASE_CLIENTS_TABLE: str = os.getenv("SUPABASE_CLIENTS_TABLE", "api_credentials")
    
    # CORS Configuration
    BACKEND_CORS_ORIGINS: list = ["*"]
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    class Config:
        case_sensitive = True
        env_file = ".env"

# Initialize settings and log configuration
settings = Settings()

# Log configuration for debugging
logger.info(f"Settings initialized - DEBUG: {settings.DEBUG}")
logger.info(f"SUPABASE_URL configured: {bool(settings.SUPABASE_URL)}")
logger.info(f"SUPABASE_KEY configured: {bool(settings.SUPABASE_KEY)}")
logger.info(f"SUPABASE_CLIENTS_TABLE: {settings.SUPABASE_CLIENTS_TABLE}")
logger.info(f"SECRET_KEY configured: {bool(settings.SECRET_KEY)}")
logger.info(f"ACCESS_TOKEN_EXPIRE_MINUTES: {settings.ACCESS_TOKEN_EXPIRE_MINUTES}") 