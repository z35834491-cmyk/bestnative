# ============================================================
# app/agents/llm.py — OpenAI 兼容 LLM 客户端（单例，懒加载）
# ============================================================

from app.core.config import settings

_llm = None


def get_llm(temperature: float | None = None):
    """返回 LangChain ChatOpenAI，对接任意 OpenAI 兼容推理端点。"""
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
    return _llm
