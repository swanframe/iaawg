import json
import re
from abc import ABC, abstractmethod
from groq import Groq
from cerebras.cloud.sdk import Cerebras
from config.settings import settings, get_setting

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_content(self, prompt: str, system_instruction: str) -> tuple[str, int, int]:
        pass

class GroqProvider(BaseLLMProvider):
    def __init__(self):
        api_key = get_setting("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY tidak ditemukan (tidak ada di DB maupun .env)")
        self.client = Groq(api_key=api_key)
        self.model = get_setting("DEFAULT_MODEL") or settings.DEFAULT_MODEL

    def generate_content(self, prompt: str, system_instruction: str) -> tuple[str, int, int]:
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=4000
            )
            return completion.choices[0].message.content, completion.usage.prompt_tokens, completion.usage.completion_tokens
        except Exception as e:
            print(f"[LLM Error] Terjadi kendala pada Groq API: {e}")
            return "", 0, 0

class CerebrasProvider(BaseLLMProvider):
    def __init__(self):
        api_key = get_setting("CEREBRAS_API_KEY")
        if not api_key:
            raise ValueError("CEREBRAS_API_KEY tidak ditemukan (tidak ada di DB maupun .env)")
        self.client = Cerebras(api_key=api_key)
        self.model = get_setting("CEREBRAS_MODEL") or settings.CEREBRAS_MODEL

    def generate_content(self, prompt: str, system_instruction: str) -> tuple[str, int, int]:
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=4000
            )
            return completion.choices[0].message.content, completion.usage.prompt_tokens, completion.usage.completion_tokens
        except Exception as e:
            print(f"[LLM Error] Terjadi kendala pada Cerebras API: {e}")
            return "", 0, 0

# === ENGINE FAILOVER DINAMIS ===
class FailoverLLMProvider(BaseLLMProvider):
    def __init__(self, provider_chain_str: str = None):
        # Menerima string kombinasi seperti: "groq,cerebras"
        self.chain_str = provider_chain_str or settings.DEFAULT_LLM_PROVIDER

    def generate_content(self, prompt: str, system_instruction: str) -> tuple[str, int, int]:
        # Peta kelas provider yang terdaftar
        provider_mapping = {
            "groq": GroqProvider,
            "cerebras": CerebrasProvider,
        }

        # Parsing string kombinasi urutan model menjadi list
        requested_chain = [p.strip().lower() for p in self.chain_str.split(",") if p.strip()]

        # Susun rantai eksekusi failover secara otomatis
        provider_chain = []
        for name in requested_chain:
            if name in provider_mapping:
                provider_chain.append((name, provider_mapping[name]))

        # Fallback jika input chain kosong/tidak valid
        if not provider_chain:
            provider_chain = [("groq", GroqProvider), ("cerebras", CerebrasProvider)]

        errors = []
        for name, provider_cls in provider_chain:
            try:
                print(f"[LLM Core] Mencoba memproses konten menggunakan provider: {name.upper()}...")
                provider_instance = provider_cls()
                content, p_tokens, c_tokens = provider_instance.generate_content(prompt, system_instruction)

                if content and not ("rate_limit_exceeded" in content.lower() or "429" in content):
                    return content, p_tokens, c_tokens
                else:
                    raise ValueError(f"Response kosong atau tidak valid dari {name.upper()}")
            except Exception as e:
                err_msg = f"Provider {name.upper()} mengalami kendala: {str(e)}"
                print(f"[LLM Backup Warning] {err_msg}")
                errors.append(err_msg)
                print("[LLM Backup] Mengalihkan proses secara otomatis ke provider cadangan berikutnya...")

        print(f"[LLM Fatal Error] Seluruh provider pada rantai failover gagal diproses: {errors}")
        return "", 0, 0

def get_llm_provider(provider_name: str = None) -> BaseLLMProvider:
    return FailoverLLMProvider(provider_name)
