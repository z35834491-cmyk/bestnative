# ============================================================
# app/core/config.py — 全局配置（pydantic-settings）
# 单环境部署：每个环境独立部署一个实例，ENVIRONMENT 由部署时注入
# ============================================================

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    APP_NAME: str = "BestNative"
    APP_VERSION: str = "0.1.0"
    # 当前实例所属环境（部署时注入，用于展示与资源发现范围）
    ENVIRONMENT: Literal["test", "prod", "futures", "development"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ---- Database (PostgreSQL + pgvector) ----
    DATABASE_URL: str = "postgresql+asyncpg://bestnative:bestnative@localhost:5432/bestnative"
    DATABASE_URL_SYNC: str = "postgresql://bestnative:bestnative@localhost:5432/bestnative"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # ---- Redis (缓存 + Pub/Sub，替代 Kafka/Celery) ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- Observability ----
    PROMETHEUS_URL: str = "http://localhost:9090"
    # Elasticsearch (日志检索，复用现有 ES)
    ES_HOST: str = ""
    ES_PORT: int = 9200
    ES_USER: str = "elastic"
    ES_PASSWORD: str = ""

    # ---- LLM (DeepSeek，复用现有 Key) ----
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 4096

    # ---- RAG (本地 embedding / rerank，零 API 费) ----
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    EMBEDDING_DIM: int = 512
    RAG_TOP_K: int = 10
    RAG_RERANK_TOP_N: int = 3

    # ---- Auth (JWT) ----
    # 生产必须通过环境变量注入，禁止使用默认值
    SECRET_KEY: str = Field(default="dev-only-insecure-key-change-in-production-min-32c")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480  # 8h

    # ---- Infra Discovery ----
    KUBECONFIG: str = ""            # 空则用集群内 ServiceAccount / 默认 ~/.kube/config
    K8S_IN_CLUSTER: bool = False    # 部署到 K8s 内时设为 True
    K8S_CONTEXT: str = ""           # kubeconfig context，如 "test"；空则用 current-context
    CLUSTER_NAME: str = "default"   # 集群名称（前端展示用；配置为本环境实际名称）
    DISCOVERY_INTERVAL: int = 300   # 自动发现周期（秒）

    # ---- Security Scan (合并自 PentestAgent) ----
    SCAN_TOOLS_PATH: str = "/usr/local/bin"
    SCAN_TIMEOUT: int = 3600
    MAX_CONCURRENT_SCANS: int = 3
    # 全平台自动扫描周期（cron 表达式，每天凌晨3点）
    AUTO_SCAN_CRON: str = "0 3 * * *"

    # ---- 发布管理 (GitLab CI / ArgoCD) ----
    GITLAB_WEBHOOK_TOKEN: str = ""      # webhook 校验 token（安全）
    ARGOCD_SERVER: str = ""
    ARGOCD_TOKEN: str = ""
    DEPLOY_VERIFY_WAIT: int = 60        # 部署后验证等待秒数
    AUTO_ROLLBACK: bool = True         # 验证失败自动回滚

    # ---- CORS ----
    CORS_ORIGINS: list[str] = ["http://localhost:3456"]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
