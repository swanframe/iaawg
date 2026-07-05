import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    DEFAULT_LLM_PROVIDER: str = "groq"
    DEFAULT_MODEL: str = "llama-3.1-8b-instant"
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"
    )

settings = Settings()