# ============================================================
# app/tools/registry.py — 分层工具注册表（22 工具，4 层加载）
# 每层只在对应阶段注入 LLM，节约 token
# ============================================================

from dataclasses import dataclass
from enum import IntEnum
from typing import Awaitable, Callable


class ToolTier(IntEnum):
    T0_ALWAYS = 0    # 常驻：可观测性核心
    T1_PLAN = 1      # 计划阶段：变更/历史/事件
    T2_ANALYZE = 2   # 分析阶段：深度检查
    T3_ACTION = 3    # 输出阶段：安全/成本/生成规则


@dataclass
class Tool:
    name: str
    tier: ToolTier
    description: str
    func: Callable[..., Awaitable]
    schema: dict  # OpenAI function-calling schema


_TOOLS: dict[str, Tool] = {}


def register_tool(name: str, tier: ToolTier, description: str, schema: dict):
    def deco(func: Callable[..., Awaitable]):
        _TOOLS[name] = Tool(name=name, tier=tier, description=description, func=func, schema=schema)
        return func
    return deco


def get_tools_for_tier(max_tier: ToolTier) -> list[Tool]:
    """返回 <= max_tier 的工具（分阶段累加加载）。"""
    return [t for t in _TOOLS.values() if t.tier <= max_tier]


def get_tools_at_tier(tier: ToolTier) -> list[Tool]:
    return [t for t in _TOOLS.values() if t.tier == tier]


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def all_schemas(max_tier: ToolTier) -> list[dict]:
    """给 LLM 的 function schema 列表（只含当前阶段可用工具）。"""
    return [{"type": "function", "function": t.schema} for t in get_tools_for_tier(max_tier)]
