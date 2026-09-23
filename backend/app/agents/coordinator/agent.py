# ============================================================
# app/agents/coordinator/agent.py — 调度 Agent（多 Agent 编排）
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.architecture.agent import ArchitectureAgent
from app.agents.base import AgentConfig, BaseAgent
from app.agents.cost.agent import CostAgent
from app.agents.diagnosis.agent import DiagnosisAgent
from app.agents.knowledge.agent import KnowledgeAgent
from app.agents.monitor.agent import MonitorAgent
from app.agents.remediate.agent import RemediateAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.incident import Incident
from app.models.schedule import Schedule
from app.services.agent_runs import finish_run, start_run

logger = get_logger("agent.coordinator")


class CoordinatorAgent(BaseAgent):
    config = AgentConfig(name="coordinator", system_prompt="多 Agent 任务编排")

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_pipeline(self, pipeline: str, context: dict | None = None) -> dict:
        context = context or {}
        run = await start_run(
            self.db,
            agent_type="coordinator",
            title=f"编排: {pipeline}",
            triggered_by=context.get("triggered_by", "manual"),
            input={"pipeline": pipeline, **context},
        )
        steps: list[dict] = []
        try:
            if pipeline == "incident_response":
                steps = await self._incident_response(context)
            elif pipeline == "daily_ops":
                steps = await self._daily_ops()
            elif pipeline == "on_call_check":
                steps = await self._on_call_check()
            else:
                raise ValueError(f"unknown pipeline: {pipeline}")

            output = {"pipeline": pipeline, "steps": steps, "completedAt": datetime.now(timezone.utc).isoformat()}
            await finish_run(self.db, run, output)
            return {"runId": str(run.id), **output}
        except Exception as exc:  # noqa: BLE001
            await finish_run(self.db, run, {"steps": steps}, error=str(exc)[:500])
            raise

    async def _incident_response(self, ctx: dict) -> list[dict]:
        incident_id = ctx.get("incident_id", "")
        steps = []

        if incident_id and settings.llm_configured:
            inc = (await self.db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
            if inc:
                diag = await DiagnosisAgent(self.db).run({
                    "title": inc.title,
                    "severity": inc.severity,
                    "affected_services": inc.affected_services or [],
                    "alert_detail": inc.extra,
                })
                steps.append({"agent": "diagnosis", "status": "done", "confidence": diag.get("confidence")})

                if diag.get("can_auto_fix"):
                    plan = await RemediateAgent(self.db).plan(incident_id, triggered_by="coordinator")
                    steps.append({"agent": "remediate", "status": "done", "actions": len(plan.get("actions", []))})

        return steps

    async def _daily_ops(self) -> list[dict]:
        steps = []
        if settings.MONITOR_PATROL_ENABLED:
            patrol = await MonitorAgent(self.db).patrol(triggered_by="coordinator")
            steps.append({"agent": "monitor", "status": "done", "issues": len(patrol.get("issues", []))})
        if settings.COST_ANALYSIS_ENABLED:
            cost = await CostAgent(self.db).analyze(triggered_by="coordinator")
            steps.append({"agent": "cost", "status": "done", "totalUsd": cost.get("totalMonthlyUsd")})
        return steps

    async def _on_call_check(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        rows = (
            await self.db.execute(
                select(Schedule).where(Schedule.shift_date <= now).order_by(Schedule.shift_date.desc()).limit(5)
            )
        ).scalars().all()
        return [{
            "agent": "schedule",
            "status": "done",
            "onCall": [{"userId": str(r.user_id), "shift": r.shift_type, "date": r.shift_date.isoformat()} for r in rows],
        }]

    async def run(self, context: dict) -> dict:
        return await self.run_pipeline(context.get("pipeline", "daily_ops"), context)
