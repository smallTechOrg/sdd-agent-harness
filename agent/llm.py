"""Runtime LLM accessor — one init_chat_model behind config (harness/patterns/model-and-providers.md).

Switching provider/model is a config change (APP_LLM_PROVIDER/_MODEL), never a code change. The rest of the
agent never imports a provider SDK — that's the point.
"""
from langchain.chat_models import init_chat_model

from .config import get_settings


def get_model():
    s = get_settings()
    if not s.llm_api_key:
        raise RuntimeError("APP_LLM_API_KEY is required for a real run (see README / spec/tech-stack.md).")
    return init_chat_model(s.llm_model, model_provider=s.llm_provider, api_key=s.llm_api_key)
