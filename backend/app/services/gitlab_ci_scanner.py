# ============================================================
# app/services/gitlab_ci_scanner.py — GitLab CI 只读扫描（无需改 .gitlab-ci.yml）
# ============================================================

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.build_failure import classify_failure_kind, fetch_pod_startup_logs, tail_ci_log
from app.services.build_ingest import clear_service_deployments, ingest_build_record
from app.services.pipeline_time import gitlab_updated_after_param, is_pipeline_fresh, pipeline_updated_at
from app.services.build_observer import finalize_success_build, process_build

logger = get_logger("gitlab_ci_scanner")


def _gitlab_base() -> str:
    url = (settings.GITLAB_URL or "").strip().rstrip("/")
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return f"https://{url}"


class GitLabClient:
    def __init__(self):
        self.base = _gitlab_base()
        self.token = settings.GITLAB_TOKEN
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.base and self.token)

    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self.token}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base,
                headers=self._headers(),
                timeout=httpx.Timeout(60.0, connect=10.0, read=60.0, write=30.0, pool=10.0),
                verify=settings.GITLAB_SSL_VERIFY,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get(self, path: str, params: dict | None = None) -> Any:
        client = await self._get_client()
        resp = await client.get(path, params=params or {})
        resp.raise_for_status()
        return resp.json()

    async def get_text(self, path: str) -> str:
        client = await self._get_client()
        resp = await client.get(path)
        resp.raise_for_status()
        return resp.text

    async def list_projects(self) -> list[dict]:
        projects: list[dict] = []
        group_ids = [g.strip() for g in settings.GITLAB_GROUP_ID.split(",") if g.strip()]
        for gid in group_ids:
            page = 1
            while True:
                batch = await self.get(
                    f"/api/v4/groups/{gid}/projects",
                    {"include_subgroups": "true", "per_page": 100, "page": page, "simple": "true"},
                )
                if not batch:
                    break
                projects.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
        for path in settings.gitlab_project_list():
            try:
                enc = path.replace("/", "%2F")
                proj = await self.get(f"/api/v4/projects/{enc}")
                projects.append(proj)
            except Exception as exc:  # noqa: BLE001
                logger.warning("gitlab.project.fetch.failed", path=path, error=str(exc)[:80])
        # 去重
        seen: set[int] = set()
        out: list[dict] = []
        for p in projects:
            pid = p.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                out.append(p)
        return out

    async def list_latest_finished_pipeline(self, project_id: int) -> dict | None:
        """取项目最近 N 小时内最新一条已结束 pipeline。"""
        raw = await self.get(
            f"/api/v4/projects/{project_id}/pipelines",
            {
                "order_by": "updated_at",
                "sort": "desc",
                "per_page": 10,
                "updated_after": gitlab_updated_after_param(),
            },
        )
        terminal = {"success", "failed", "canceled", "skipped"}
        for p in raw:
            if p.get("status") in terminal and is_pipeline_fresh(p):
                return p
        return None

    async def list_finished_pipelines(self, project_id: int, ref: str) -> list[dict]:
        raw = await self.get(
            f"/api/v4/projects/{project_id}/pipelines",
            {
                "ref": ref,
                "order_by": "updated_at",
                "sort": "desc",
                "per_page": max(5, settings.GITLAB_CI_PIPELINES_PER_REF * 3),
            },
        )
        terminal = {"success", "failed", "canceled", "skipped"}
        done = [p for p in raw if p.get("status") in terminal]
        return done[: settings.GITLAB_CI_PIPELINES_PER_REF]

    async def list_jobs(self, project_id: int, pipeline_id: int) -> list[dict]:
        return await self.get(f"/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs")

    async def job_trace_tail(self, project_id: int, job_id: int, max_chars: int = 8000) -> str:
        try:
            text = await self.get_text(f"/api/v4/projects/{project_id}/jobs/{job_id}/trace")
            return text[-max_chars:] if text else ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("gitlab.trace.failed", job_id=job_id, error=str(exc)[:80])
            return ""


def _pipeline_status(jobs: list[dict]) -> str:
    statuses = [
        j.get("status", "")
        for j in jobs
        if j.get("stage") not in {".post", "trigger"}
    ]
    if not statuses:
        return "success"
    if any(s == "failed" for s in statuses):
        return "failed"
    if any(s == "canceled" for s in statuses):
        return "canceled"
    return "success"


def _stages_from_jobs(jobs: list[dict]) -> list[dict]:
    return [
        {
            "name": j.get("name", "unknown"),
            "duration_sec": int(j.get("duration") or 0),
            "status": j.get("status", "success"),
        }
        for j in jobs
        if j.get("stage") not in {".post", "trigger"}
    ]


async def scan_project(client: GitLabClient, project: dict, branches: list[str]) -> dict:
    pid = project["id"]
    name = project.get("path") or project.get("name", "")
    path = project.get("path_with_namespace") or name
    ingested = 0
    skipped = 0
    errors = 0

    try:
        pl = await client.list_latest_finished_pipeline(pid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("gitlab.pipelines.failed", project=path, error=str(exc)[:100])
        return {"project": path, "ingested": 0, "skipped": 0, "errors": 1}

    if not pl:
        async with AsyncSessionLocal() as db:
            cleared = await clear_service_deployments(db, name)
        return {"project": path, "ingested": 0, "skipped": 0, "errors": 0, "cleared": cleared}

    pl_id = pl.get("id")
    ref = pl.get("ref") or (branches[0] if branches else "main")
    pl_updated = pipeline_updated_at(pl)
    pl_updated_iso = pl_updated.isoformat() if pl_updated else ""
    if not pl_id:
        return {"project": path, "ingested": 0, "skipped": 0, "errors": 0}

    try:
        jobs = await client.list_jobs(pid, pl_id)
        status = _pipeline_status(jobs)
        stages = _stages_from_jobs(jobs)
        duration = int(pl.get("duration") or sum(s["duration_sec"] for s in stages) or 0)
        fail_log = ""
        failure_kind = "build"
        failed_job = None
        if status == "failed":
            failed_job = next((j for j in jobs if j.get("status") == "failed"), None)
            if failed_job:
                failure_kind = classify_failure_kind(failed_job)
                if failure_kind == "startup":
                    fail_log = fetch_pod_startup_logs(name, ref)
                    if not fail_log:
                        fail_log = tail_ci_log(await client.job_trace_tail(pid, failed_job["id"]))
                else:
                    fail_log = tail_ci_log(await client.job_trace_tail(pid, failed_job["id"]))

        sha = (pl.get("sha") or "")[:8]
        version = f"{ref}-{sha}" if sha else str(pl_id)
        commit_message = ""
        if pl.get("sha"):
            try:
                commit = await client.get(f"/api/v4/projects/{pid}/repository/commits/{pl['sha']}")
                commit_message = (commit.get("title") or commit.get("message") or "")[:500]
            except Exception:  # noqa: BLE001
                pass

        async with AsyncSessionLocal() as db:
            did, is_new = await ingest_build_record(
                db,
                service=name,
                project=path,
                status=status,
                version=version,
                duration_sec=duration,
                stages=stages,
                failure_log=fail_log,
                argocd_app=name,
                triggered_by="gitlab-scanner",
                commit_message=commit_message,
                ci_job_url=pl.get("web_url", ""),
                pipeline_id=str(pl_id),
                gitlab_project_id=str(pid),
                branch=ref,
                pipeline_updated_at=pl_updated_iso,
                extra={"gitlab_pipeline_iid": pl.get("iid"), "scan_source": "gitlab_api", "failure_kind": failure_kind},
            )
            if not is_new:
                skipped += 1
            else:
                ingested += 1
                if status == "failed":
                    await process_build(db, did)
                else:
                    await finalize_success_build(db, did, name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("gitlab.pipeline.ingest.failed", project=path, pipeline=pl_id, error=str(exc)[:120])
        errors += 1

    return {"project": path, "ingested": ingested, "skipped": skipped, "errors": errors}


async def run_gitlab_ci_scan() -> dict:
    if not settings.GITLAB_CI_SCAN_ENABLED:
        return {"status": "disabled"}
    client = GitLabClient()
    if not client.enabled:
        return {"status": "skipped", "reason": "GITLAB_URL / GITLAB_TOKEN 未配置"}

    branches = settings.gitlab_ci_branches()
    summary = {"status": "ok", "projects": 0, "ingested": 0, "skipped": 0, "errors": 0, "details": []}
    try:
        projects = await client.list_projects()
        summary["projects"] = len(projects)
        for proj in projects:
            r = await scan_project(client, proj, branches)
            summary["ingested"] += r["ingested"]
            summary["skipped"] += r["skipped"]
            summary["errors"] += r["errors"]
            if r["ingested"]:
                summary["details"].append(r)
        logger.info("gitlab.scan.done", **{k: summary[k] for k in ("projects", "ingested", "skipped", "errors")})
    finally:
        await client.close()
    return summary
