# ============================================================
# app/schemas/security.py
# ============================================================

from pydantic import BaseModel


class ScanRequest(BaseModel):
    target: str = ""              # 手动扫描的域名/IP（逗号分隔）；全平台可留空
    scope: str = "manual"         # manual / full_platform
    triggered_by: str = "manual"
