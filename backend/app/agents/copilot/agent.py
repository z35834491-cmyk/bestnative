# ============================================================
# app/agents/copilot/agent.py — 运维助手 Agent（对话）
# ============================================================

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, BaseAgent
from app.agents.react import run_react
from app.core.config import settings
from app.services.environments import get_active_profile
from app.tools.registry import ToolTier

SYSTEM_PROMPT = """你是 Shore 平台的运维助手。帮用户查服务状态、指标、日志、事件和知识库。
回答要具体、可操作，基于工具返回的真实数据。不知道就说不知道，别编。
当前环境：{environment}"""


class CopilotAgent(BaseAgent):
    config = AgentConfig(
        name="copilot",
        system_prompt=SYSTEM_PROMPT,
        max_tier=ToolTier.T2_ANALYZE,
        max_iterations=6,
        temperature=0.3,
    )

    def __init__(self, db: AsyncSession):
        self.db = db

    async def chat(self, message: str, history: list[dict] | None = None) -> dict:
        history = history or []
        context_lines = []
        for h in history[-6:]:
            role = h.get("role", "user")
            content = (h.get("content") or "")[:500]
            context_lines.append(f"{role}: {content}")
        prefix = "\n".join(context_lines)
        task = f"{prefix}\nuser: {message}" if prefix else message

        if not settings.llm_configured:
            return {
                "reply": "未配置 LLM（LLM_API_KEY）。请在 backend/.env.secrets 中配置 OpenAI 兼容 API。",
                "tokens": 0,
                "toolCalls": [],
            }

        profile = get_active_profile()
        prompt = self.config.system_prompt.format(environment=f"{profile.label} ({profile.id})")
        result = await run_react(
            system_prompt=prompt,
            user_task=task,
            max_tier=self.config.max_tier,
            max_iterations=self.config.max_iterations,
        )
        return {
            "reply": result.get("final_answer", ""),
            "tokens": result.get("tokens", 0),
            "toolCalls": result.get("tool_calls", []),
        }

    async def run(self, context: dict) -> dict:
        return await self.chat(context.get("message", ""), context.get("history"))
