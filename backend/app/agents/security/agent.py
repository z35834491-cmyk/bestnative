# ============================================================
# app/agents/security/agent.py — 安全 Agent（扫描编排 + AI 分析）
# 流程：目标解析 → subfinder → httpx → nmap → nuclei
#       → AI 汇总分析 → 漏洞入库 → 高危自动建 Incident
# 两种触发：full_platform（全平台巡检）/ manual（手动输入域名）
# ============================================================

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import get_llm
from app.core.logging import get_logger
from app.models.infra import Middleware, Node, Service
from app.models.security import Asset, ScanSession, Vulnerability
from app.tools.scanners import SCANNERS

logger = get_logger("agent.security")


class SecurityAgent:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def scan(self, session_id: str) -> dict:
        """执行一次扫描会话（由 API 预创建 ScanSession 后调用）。"""
        session = (await self.db.execute(
            select(ScanSession).where(ScanSession.id == session_id)
        )).scalar_one_or_none()
        if session is None:
            return {"error": "scan session not found"}

        session.status = "recon"
        session.started_at = datetime.now(timezone.utc)
        await self.db.flush()

        # 1. 确定扫描目标
        if session.scope == "full_platform":
            targets = await self._collect_platform_targets()
        else:
            targets = [t.strip() for t in session.target.split(",") if t.strip()]

        logger.info("security.scan.start", session=session_id, targets=len(targets))

        all_assets: list[dict] = []
        all_vulns: list[dict] = []

        for target in targets:
            # 2. 资产发现（域名 → 子域名 → 存活探测）
            session.status = "discovery"
            await self.db.flush()
            assets = await self._discover_assets(target)
            all_assets.extend(assets)

            # 3. 漏洞扫描（nmap 端口 + nuclei CVE）
            session.status = "vuln_scan"
            await self.db.flush()
            scan_targets = [target] + [a["value"] for a in assets if a["type"] in ("subdomain", "url")]
            vulns = await self._scan_vulns(scan_targets[:20])  # 限制目标数
            all_vulns.extend(vulns)

        # 4. 持久化资产 + 漏洞
        for a in all_assets:
            self.db.add(Asset(session_id=session_id, type=a["type"], value=a["value"],
                              port=a.get("port"), service=a.get("service", ""),
                              version=a.get("version", ""), extra=a.get("extra", {})))
        for v in all_vulns:
            self.db.add(Vulnerability(
                session_id=session_id, title=v["title"], severity=v["severity"],
                type=v.get("type", ""), target=v.get("target", ""),
                endpoint=v.get("endpoint", ""), found_by=v.get("found_by", "nuclei"),
                cve=v.get("cve") or "", cvss_score=v.get("cvss_score"),
                description=v.get("description", ""), recommendation=v.get("recommendation", ""),
            ))

        # 5. AI 汇总分析 → 报告
        session.status = "analyzing"
        await self.db.flush()
        report = await self._ai_report(session.target, all_assets, all_vulns)

        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
        session.asset_count = len(all_assets)
        session.vuln_count = len(all_vulns)
        session.report = report
        await self.db.flush()

        logger.info("security.scan.done", session=session_id,
                    assets=len(all_assets), vulns=len(all_vulns))
        return {"session_id": session_id, "assets": len(all_assets),
                "vulns": len(all_vulns), "report": report}

    async def _collect_platform_targets(self) -> list[str]:
        """全平台巡检：从已发现的服务/中间件/节点收集扫描目标。"""
        targets: set[str] = set()
        middlewares = (await self.db.execute(select(Middleware))).scalars().all()
        for m in middlewares:
            if m.host:
                targets.add(m.host)
        nodes = (await self.db.execute(select(Node))).scalars().all()
        for n in nodes:
            if n.internal_ip:
                targets.add(n.internal_ip)
        return list(targets)

    async def _discover_assets(self, target: str) -> list[dict]:
        assets: list[dict] = []
        # IP 目标跳过子域名枚举
        if not _is_ip(target):
            subs = await SCANNERS["subfinder"].run(target)
            assets.extend(subs)
            probe_targets = [target] + [s["value"] for s in subs][:30]
        else:
            probe_targets = [target]
        # httpx 存活探测
        for t in probe_targets:
            live = await SCANNERS["httpx"].run(t)
            assets.extend(live)
        return assets

    async def _scan_vulns(self, targets: list[str]) -> list[dict]:
        vulns: list[dict] = []
        for t in targets:
            # 端口扫描（IP/域名）
            ports = await SCANNERS["nmap"].run(t, options={"ports": "1-10000"})
            # CVE 扫描
            url = t if t.startswith("http") else f"http://{t}"
            found = await SCANNERS["nuclei"].run(url)
            vulns.extend(found)
        return vulns

    async def _ai_report(self, target: str, assets: list[dict], vulns: list[dict]) -> str:
        """DeepSeek 汇总扫描结果，生成中文安全报告。"""
        if not vulns and not assets:
            return "本次扫描未发现资产或漏洞。"
        sev_count: dict[str, int] = {}
        for v in vulns:
            sev_count[v["severity"]] = sev_count.get(v["severity"], 0) + 1
        summary = f"目标：{target}\n资产数：{len(assets)}\n漏洞分布：{sev_count}\n"
        top_vulns = "\n".join(
            f"- [{v['severity']}] {v['title']} @ {v.get('endpoint', v.get('target', ''))}"
            for v in sorted(vulns, key=lambda x: x["severity"])[:15]
        )
        prompt = f"""你是安全专家。基于以下扫描结果生成简洁中文安全报告，
包含：风险概述、重点漏洞、修复优先级建议。

{summary}
重点漏洞：
{top_vulns}"""
        try:
            from langchain_core.messages import HumanMessage
            llm = get_llm(temperature=0.3)
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            return resp.content
        except Exception as e:  # noqa: BLE001
            logger.warning("security.report.failed", error=str(e))
            return summary + top_vulns


def _is_ip(s: str) -> bool:
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
