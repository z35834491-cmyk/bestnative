# ============================================================
# app/agents/llm.py — DeepSeek LLM 客户端（单例，懒加载）
# ============================================================

from app.core.config import settings

_llm = None


def get_llm(temperature: float | None = None):
    """返回 LangChain ChatOpenAI（指向 DeepSeek）。"""
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
    return _llm
