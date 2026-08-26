# ============================================================
# app/schemas/deployment.py
# ============================================================

from typing import Any

from pydantic import BaseModel, Field


class BuildStage(BaseModel):
    name: str
    duration_sec: float = 0
    status: str = "success"  # success | failed | skipped
    log_excerpt: str = ""


class DeploymentConfigUpdate(BaseModel):
    auto_rollback: bool | None = None


class DeployWebhook(BaseModel):
    """GitLab CI 构建完成回调 — 外挂观测，不改变现有 CI/CD 流程。"""

    service: str
    project: str = ""
    status: str = "success"  # success | failed | canceled
    version: str = ""
    previous_version: str = ""
    duration_sec: int = 0
    stages: list[BuildStage] = Field(default_factory=list)
    failure_log: str = ""
    docker_image: str = ""
    argocd_app: str = ""
    triggered_by_user: str = ""
    commit_message: str = ""
    ci_job_url: str = ""
    pipeline_id: str = ""
    job_id: str = ""
    # 兼容旧「接管部署」模式；默认 False，仅观测
    takeover_deploy: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)
