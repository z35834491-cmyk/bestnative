# ============================================================
# app/agents/knowledge/agent.py — 知识 Agent（归档、增强入库）
# ============================================================

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, BaseAgent
from app.agents.llm import get_llm
from app.core.config import settings
from app.core.logging import get_logger
from app.models.incident import AnalysisReport, Incident, IncidentEvent
from app.models.knowledge import KnowledgeChunk
from app.rag.ingest import ingest
from app.services.agent_runs import finish_run, start_run

logger = get_logger("agent.knowledge")


class KnowledgeAgent(BaseAgent):
    config = AgentConfig(name="knowledge", system_prompt="知识归档与检索增强")

    def __init__(self, db: AsyncSession):
        self.db = db

    async def archive_incident(self, incident_id: str, *, triggered_by: str = "manual") -> dict:
        run = await start_run(
            self.db,
            agent_type="knowledge",
            title=f"知识归档 #{incident_id[:8]}",
            triggered_by=triggered_by,
            input={"incidentId": incident_id},
        )
        inc = (await self.db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
        if inc is None:
            await finish_run(self.db, run, {}, error="incident not found")
            return {"error": "incident not found"}

        report = (
            await self.db.execute(
                select(AnalysisReport)
                .where(AnalysisReport.incident_id == incident_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        events = (
            await self.db.execute(
                select(IncidentEvent)
                .where(IncidentEvent.incident_id == incident_id)
                .order_by(IncidentEvent.created_at)
            )
        ).scalars().all()

        report_dict = {
            "root_cause": report.root_cause if report else "",
            "recommendation": report.recommendation if report else "",
            "evidence": report.evidence if report else [],
        }
        content = await self._enrich_content(inc, report_dict, events)
        chunks = await ingest(
            self.db,
            source_type="incident_resolution",
            title=inc.title,
            content=content,
            source_id=str(inc.id),
            metadata={
                "services": inc.affected_services or [],
                "severity": inc.severity,
                "status": inc.status,
            },
        )
        output = {"incidentId": incident_id, "chunksIngested": chunks, "title": inc.title}
        await finish_run(self.db, run, output)
        return {"runId": str(run.id), **output}

    async def stats(self) -> dict:
        rows = (
            await self.db.execute(
                select(KnowledgeChunk.source_type, func.count())
                .group_by(KnowledgeChunk.source_type)
            )
        ).all()
        total = sum(c for _, c in rows)
        return {
            "totalChunks": total,
            "bySourceType": {st: cnt for st, cnt in rows},
        }

    async def _enrich_content(self, inc: Incident, report: dict, events) -> str:
        timeline = "\n".join(f"- [{e.created_at}] {e.actor}: {e.content}" for e in events[-20:])
        base = f"""# {inc.title}

严重程度：{inc.severity}
服务：{', '.join(inc.affected_services or [])}
根因：{report.get('root_cause', '')}
建议：{report.get('recommendation', '')}
证据：{json.dumps(report.get('evidence', []), ensure_ascii=False)}

## 时间线
{timeline}
"""
        if not settings.llm_configured:
            return base

        try:
            from langchain_core.messages import HumanMessage
            llm = get_llm(temperature=0.2)
            prompt = f"""将以下故障信息整理为知识库条目（中文，300-600字）：
包含：现象、根因、修复步骤、预防建议。不要编造。

{base}"""
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            if resp.content and len(resp.content.strip()) > 80:
                return resp.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.debug("knowledge.enrich.failed", error=str(exc)[:80])
        return base

    async def run(self, context: dict) -> dict:
        return await self.archive_incident(
            context.get("incident_id", ""),
            triggered_by=context.get("triggered_by", "manual"),
        )
