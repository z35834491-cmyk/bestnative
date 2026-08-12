# ============================================================
# app/agents/base.py — Agent 基类（可插拔）
# 每个 Agent = system_prompt + 工具层 + 触发条件
# ============================================================

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.tools.registry import ToolTier


@dataclass
class AgentConfig:
    name: str
    system_prompt: str
    max_tier: ToolTier = ToolTier.T0_ALWAYS
    max_iterations: int = 8
    requires_approval: bool = False
    temperature: float = 0.3


class BaseAgent(ABC):
    """所有 Agent 的抽象基类。子类声明 config 与 run。"""

    config: AgentConfig

    @abstractmethod
    async def run(self, context: dict) -> dict:
        """执行 Agent 任务，返回结构化结果。"""
        ...
