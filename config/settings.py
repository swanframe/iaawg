import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    CEREBRAS_API_KEY: str = ""
    GITHUB_TOKEN: str = ""      # API Token/PAT dari GitHub Models
    
    DEFAULT_LLM_PROVIDER: str = "groq,cerebras,github" # Default chain order
    DEFAULT_MODEL: str = "llama-3.1-8b-instant"
    CEREBRAS_MODEL: str = "gemma-4-31b"
    GITHUB_MODEL: str = "gpt-4o-mini"    # Model GitHub pilihan Anda
    
    # WordPress API Configuration
    WP_URL: str = ""
    WP_USERNAME: str = ""
    WP_APPLICATION_PASSWORD: str = ""
    
    # Visual & Design Configuration
    UNSPLASH_API_KEY: str = ""
    DEFAULT_IMAGE_PROVIDER: str = "pollinations"
    DEFAULT_STOCK_PROVIDER: str = "unsplash"
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"
    )

settings = Settings()