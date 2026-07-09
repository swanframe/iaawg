import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    CEREBRAS_API_KEY: str = ""  # API Key Cerebras Cloud
    DEFAULT_LLM_PROVIDER: str = "groq"
    DEFAULT_MODEL: str = "llama-3.1-8b-instant"
    CEREBRAS_MODEL: str = "gemma-4-31b"  # Model Cerebras pilihan Anda
    
    # WordPress API Configuration
    WP_URL: str = ""           # Contoh: https://subdomain.ilogo.co.id
    WP_USERNAME: str = ""      # Username WordPress administrator / manager
    WP_APPLICATION_PASSWORD: str = ""  # Application Password dari profil WP
    
    # Visual & Design Configuration (Phase 3)
    UNSPLASH_API_KEY: str = "" # Akses Key dari Unsplash Developer
    DEFAULT_IMAGE_PROVIDER: str = "pollinations"  # Pilihan: pollinations, gpt_image, bannerbear
    DEFAULT_STOCK_PROVIDER: str = "unsplash"      # Pilihan: unsplash
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"
    )

settings = Settings()