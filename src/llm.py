import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

def get_llm(temperature: float = 0):
    """Factory function returning the configured LLM provider (OpenAI or Google GenAI)."""
    provider = os.getenv("MODEL_PROVIDER", "openai").lower()
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-1.5-pro"),
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=temperature
        )
    else:
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=temperature
        )
