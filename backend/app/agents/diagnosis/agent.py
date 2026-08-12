# ============================================================
# app/agents/diagnosis/agent.py — 诊断 Agent（根因分析）
# 流程：RAG 检索历史相似事件 → ReAct 深度分析 → 结构化根因报告
# ============================================================

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, BaseAgent
from app.agents.llm import get_llm
from app.agents.react import run_react
from app.core.logging import get_logger
from app.rag.retriever import hybrid_search
from app.tools.registry import ToolTier

logger = get_logger("agent.diagnosis")

SYSTEM_PROMPT = """你是资深 SRE 诊断专家。基于告警信息、实时指标、日志和历史相似事件，定位故障根因。
原则：
1. 先看历史相似事件的解决方案（已在上下文提供）
2. 用工具查询实时指标和日志验证假设
3. 聚焦故障服务及其直接依赖，不发散
4. 输出必须结构化：根因、证据、建议、置信度
不要编造数据，所有结论必须有工具返回的证据支撑。"""


class DiagnosisAgent(BaseAgent):
    config = AgentConfig(
        name="diagnosis",
        system_prompt=SYSTEM_PROMPT,
        max_tier=ToolTier.T2_ANALYZE,
        max_iterations=8,
        temperature=0.2,
    )

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(self, context: dict) -> dict:
        """context: {title, severity, affected_services, alert_detail}"""
        title = context.get("title", "")
        services = context.get("affected_services", [])

        # 1. RAG 检索历史相似事件
        similar = await hybrid_search(
            self.db, query=title, affected_services=services, top_n=3,
        )
        rag_context = self._format_rag(similar)

        # 2. 组装任务
        task = f"""告警：{title}
严重程度：{context.get('severity', 'warning')}
受影响服务：{', '.join(services) or '未知'}
告警详情：{json.dumps(context.get('alert_detail', {}), ensure_ascii=False)}

历史相似事件参考：
{rag_context}

请定位根因并给出处理建议。"""

        # 3. ReAct 深度分析
        result = await run_react(
            system_prompt=self.config.system_prompt,
            user_task=task,
            max_tier=self.config.max_tier,
            max_iterations=self.config.max_iterations,
        )

        # 4. 结构化输出
        report = await self._structure(result["final_answer"], similar)
        report["tokens"] = result["tokens"]
        report["tool_calls"] = result["tool_calls"]
        report["similar_incidents"] = [s["id"] for s in similar]
        return report

    def _format_rag(self, similar: list[dict]) -> str:
        if not similar:
            return "（无历史相似事件）"
        lines = []
        for i, s in enumerate(similar, 1):
            lines.append(f"{i}. [{s['source_type']}] {s['title']}\n   {s['content'][:300]}")
        return "\n".join(lines)

    async def _structure(self, answer: str, similar: list[dict]) -> dict:
        """让 LLM 把自由文本压成结构化 JSON。"""
        llm = get_llm(temperature=0)
        prompt = f"""将以下诊断结论转为 JSON，字段：root_cause(根因), evidence(证据数组),
recommendation(建议), confidence(high/medium/low), can_auto_fix(bool)。
只输出 JSON，不要解释。

诊断结论：
{answer}"""
        from langchain_core.messages import HumanMessage
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        try:
            text = resp.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1].removeprefix("json").strip()
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            data = {"root_cause": answer[:500], "evidence": [], "recommendation": "",
                    "confidence": "low", "can_auto_fix": False}
        return data
