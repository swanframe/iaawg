import os
import json
from abc import ABC, abstractmethod
from groq import Groq
from config.settings import settings

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_content(self, prompt: str, system_instruction: str) -> str:
        pass

class GroqProvider(BaseLLMProvider):
    def __init__(self):
        # Fallback jika env belum terbaca sempurna di settings
        api_key = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY tidak ditemukan di environment maupun file .env")
        self.client = Groq(api_key=api_key)
        self.model = settings.DEFAULT_MODEL

    def generate_content(self, prompt: str, system_instruction: str) -> str:
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"[LLM Error] Terjadi kendala pada Groq API: {e}")
            return ""

def get_llm_provider(provider_name: str = None) -> BaseLLMProvider:
    provider = provider_name or settings.DEFAULT_LLM_PROVIDER
    if provider.lower() == "groq":
        return GroqProvider()
    else:
        raise NotImplementedError(True, f"Provider {provider} belum diimplementasikan.")