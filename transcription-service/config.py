"""Configuration settings."""

import os
from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # API Keys
    DEEPGRAM_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    INTERNAL_API_KEY: str = ""
    
    # CORS (comma-separated origins, or * for all)
    CORS_ORIGINS: str = "*"
    
    # Service
    TRANSCRIPTION_SERVICE_PORT: int = 8010
    DEEPGRAM_MODEL: str = "nova-3"
    
    # LLM Models
    GROQ_FORMAT_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_PROMPT_MODEL: str = "meta-llama/llama-4-maverick-17b-128e-instruct"
    
    # Pricing (USD per token)
    GROQ_FORMAT_INPUT_COST: float = 0.59 / 1_000_000
    GROQ_FORMAT_OUTPUT_COST: float = 0.79 / 1_000_000
    GROQ_PROMPT_INPUT_COST: float = 0.20 / 1_000_000
    GROQ_PROMPT_OUTPUT_COST: float = 0.60 / 1_000_000
    
    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
    
    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
