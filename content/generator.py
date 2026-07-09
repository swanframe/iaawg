import os
import json
from abc import ABC, abstractmethod
from groq import Groq
from cerebras.cloud.sdk import Cerebras
from config.settings import settings

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_content(self, prompt: str, system_instruction: str) -> tuple[str, int, int]:
        pass

class GroqProvider(BaseLLMProvider):
    def __init__(self):
        api_key = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY tidak ditemukan di environment maupun file .env")
        self.client = Groq(api_key=api_key)
        self.model = settings.DEFAULT_MODEL

    def generate_content(self, prompt: str, system_instruction: str) -> tuple[str, int, int]:
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
            content = completion.choices[0].message.content
            # Ekstrak data token dari respons Groq
            prompt_tokens = completion.usage.prompt_tokens
            completion_tokens = completion.usage.completion_tokens
            
            return content, prompt_tokens, completion_tokens
        except Exception as e:
            print(f"[LLM Error] Terjadi kendala pada Groq API: {e}")
            return "", 0, 0

class CerebrasProvider(BaseLLMProvider):
    def __init__(self):
        api_key = settings.CEREBRAS_API_KEY or os.environ.get("CEREBRAS_API_KEY", "")
        if not api_key:
            raise ValueError("CEREBRAS_API_KEY tidak ditemukan di environment maupun file .env")
        self.client = Cerebras(api_key=api_key)
        self.model = settings.CEREBRAS_MODEL

    def generate_content(self, prompt: str, system_instruction: str) -> tuple[str, int, int]:
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
            content = completion.choices[0].message.content
            prompt_tokens = completion.usage.prompt_tokens
            completion_tokens = completion.usage.completion_tokens
            
            return content, prompt_tokens, completion_tokens
        except Exception as e:
            print(f"[LLM Error] Terjadi kendala pada Cerebras API: {e}")
            return "", 0, 0

class FailoverLLMProvider(BaseLLMProvider):
    def __init__(self, primary_provider: str = None):
        self.primary_provider = (primary_provider or settings.DEFAULT_LLM_PROVIDER).lower()

    def generate_content(self, prompt: str, system_instruction: str) -> tuple[str, int, int]:
        # Menentukan urutan rantai failover berdasarkan pilihan pengguna (Extensible)
        if self.primary_provider == "cerebras":
            provider_chain = [("cerebras", CerebrasProvider), ("groq", GroqProvider)]
        else:
            provider_chain = [("groq", GroqProvider), ("cerebras", CerebrasProvider)]

        errors = []
        for name, provider_cls in provider_chain:
            try:
                print(f"[LLM Core] Mencoba memproses konten menggunakan provider: {name.upper()}...")
                provider_instance = provider_cls()
                content, p_tokens, c_tokens = provider_instance.generate_content(prompt, system_instruction)
                
                # Validasi output dasar untuk memastikan response berhasil diperoleh
                if content and not ("rate_limit_exceeded" in content.lower() or "429" in content):
                    return content, p_tokens, c_tokens
                else:
                    raise ValueError(f"Response kosong atau tidak valid dari {name.upper()}")
            except Exception as e:
                err_msg = f"Provider {name.upper()} mengalami kendala: {str(e)}"
                print(f"[LLM Backup Warning] {err_msg}")
                errors.append(err_msg)
                print("[LLM Backup] Mengalihkan proses secara otomatis ke provider cadangan berikutnya...")
                continue
        
        print(f"[LLM Fatal Error] Seluruh provider pada rantai failover gagal diproses: {errors}")
        return "", 0, 0

def get_llm_provider(provider_name: str = None) -> BaseLLMProvider:
    return FailoverLLMProvider(provider_name)