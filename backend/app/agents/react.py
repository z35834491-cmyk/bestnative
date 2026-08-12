# ============================================================
# app/agents/react.py — 通用 ReAct 执行器（工具调用循环）
# 分阶段加载工具，历史对话 3 轮后摘要，控制 token
# ============================================================

import json

from app.agents.llm import get_llm
from app.core.logging import get_logger
from app.tools.registry import ToolTier, all_schemas, get_tool

logger = get_logger("agent.react")


async def run_react(system_prompt: str, user_task: str, max_tier: ToolTier,
                    max_iterations: int = 8) -> dict:
    """ReAct 循环：LLM 决策 → 调用工具 → 观察 → 再决策。

    返回 {final_answer, iterations, tool_calls, tokens}
    """
    from langchain_core.messages import (
        AIMessage, HumanMessage, SystemMessage, ToolMessage,
    )

    llm = get_llm()
    schemas = all_schemas(max_tier)
    llm_with_tools = llm.bind_tools([s["function"] for s in schemas]) if schemas else llm

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_task)]
    tool_call_log: list[dict] = []
    total_tokens = 0

    for iteration in range(max_iterations):
        response = await llm_with_tools.ainvoke(messages)
        total_tokens += _count_tokens(response)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            # 无工具调用 → 得到最终答案
            return {
                "final_answer": response.content,
                "iterations": iteration + 1,
                "tool_calls": tool_call_log,
                "tokens": total_tokens,
            }

        # 执行工具调用
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("args", {})
            tool = get_tool(name)
            if tool is None:
                result = {"error": f"unknown tool {name}"}
            else:
                try:
                    result = await tool.func(**args)
                except Exception as e:  # noqa: BLE001
                    result = {"error": str(e)}
            tool_call_log.append({"tool": name, "args": args, "result_preview": str(result)[:200]})
            messages.append(ToolMessage(
                content=json.dumps(result, ensure_ascii=False, default=str)[:2000],
                tool_call_id=tc["id"],
            ))

        # token 控制：3 轮后摘要早期历史（保留 system + 最近 4 条）
        if iteration >= 3 and len(messages) > 8:
            messages = _summarize_history(messages)

    return {
        "final_answer": "达到最大迭代次数，未收敛",
        "iterations": max_iterations,
        "tool_calls": tool_call_log,
        "tokens": total_tokens,
    }


def _count_tokens(response) -> int:
    meta = getattr(response, "response_metadata", {}) or {}
    usage = meta.get("token_usage", {}) or meta.get("usage", {})
    return usage.get("total_tokens", 0)


def _summarize_history(messages: list) -> list:
    """保留 system + 首个 user + 最近 4 条，中间压缩为一句提示。"""
    from langchain_core.messages import SystemMessage
    head = messages[:2]
    tail = messages[-4:]
    return head + [SystemMessage(content="[早期分析步骤已省略以节约上下文]")] + tail
