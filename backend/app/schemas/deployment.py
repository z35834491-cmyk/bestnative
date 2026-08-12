# ============================================================
# app/schemas/deployment.py
# ============================================================

from pydantic import BaseModel


class DeployWebhook(BaseModel):
    service: str
    version: str
    previous_version: str = ""
    docker_image: str = ""
    argocd_app: str = ""
    triggered_by_user: str = ""
    commit_message: str = ""
    ci_job_url: str = ""
