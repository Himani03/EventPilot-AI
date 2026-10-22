"""Swappable LLM adapter. Ollama is the default, local-first provider."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

class LLMError(RuntimeError):
    pass

def generate_text(prompt: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

    if provider == "ollama":
        return _ollama(prompt)

    # Optional cloud provider examples are intentionally kept commented.
    # Install the provider SDK and add its API key to .env before enabling.
    #
    # elif provider == "gemini":
    #     from google import genai
    #     client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    #     response = client.models.generate_content(
    #         model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    #         contents=prompt,
    #     )
    #     return response.text
    #
    # elif provider == "groq":
    #     from groq import Groq
    #     client = Groq(api_key=os.environ["GROQ_API_KEY"])
    #     response = client.chat.completions.create(
    #         model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    #         messages=[{"role": "user", "content": prompt}],
    #     )
    #     return response.choices[0].message.content
    #
    # elif provider == "openai":
    #     from openai import OpenAI
    #     client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    #     response = client.chat.completions.create(
    #         model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    #         messages=[{"role": "user", "content": prompt}],
    #     )
    #     return response.choices[0].message.content

    raise LLMError(
        f"Provider '{provider}' is not enabled. Set LLM_PROVIDER=ollama, "
        "or enable one of the commented provider adapters in src/llm.py."
    )

def _ollama(prompt: str) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    timeout = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))
    max_tokens = int(os.getenv("MAX_TOKENS", "900"))
    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": max_tokens},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        text = response.json().get("response", "").strip()
        if not text:
            raise LLMError("Ollama returned an empty response.")
        return text
    except requests.exceptions.ConnectionError as exc:
        raise LLMError(
            "Could not connect to Ollama. Start the Ollama app and check OLLAMA_BASE_URL."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise LLMError("The local model timed out. Try a smaller model or raise OLLAMA_TIMEOUT_SECONDS.") from exc
    except requests.RequestException as exc:
        detail = getattr(getattr(exc, "response", None), "text", str(exc))
        raise LLMError(f"Ollama request failed: {detail}") from exc
