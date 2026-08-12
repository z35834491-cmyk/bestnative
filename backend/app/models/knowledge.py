# ============================================================
# app/models/knowledge.py — RAG 知识库（pgvector 统一）
# 替代 Qdrant：向量 + 全文检索一张表解决
# ============================================================

from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base
from app.models.base import TimestampMixin


class KnowledgeChunk(TimestampMixin, Base):
    """知识块：故障复盘 / 手册 / 告警规则 / 日志模式 / K8s事件模式"""
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        # HNSW 向量索引（余弦相似度）
        Index("ix_kc_embedding", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        # GIN 全文索引
        Index("ix_kc_search", "search_vector", postgresql_using="gin"),
    )

    # incident_resolution / manual_document / alert_rule / log_pattern / k8s_event_pattern
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(400), default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBEDDING_DIM))
    search_vector: Mapped[str] = mapped_column(TSVECTOR, nullable=True)
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)  # tags/services/severity
