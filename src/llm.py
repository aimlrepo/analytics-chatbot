import os
import logging
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
logger = logging.getLogger(__name__)

def get_llm(temperature: float = 0):
    """Factory function returning the configured LLM provider (OpenAI or Google GenAI)."""
    provider = os.getenv("MODEL_PROVIDER", "openai").lower().strip()
    if provider in ("gemini", "google"):
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-pro")),
            google_api_key=os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY")),
            temperature=temperature
        )
    else:
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL_NAME", "gpt-4o")),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=temperature
        )
