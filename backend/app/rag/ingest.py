# ============================================================
# app/rag/ingest.py — 知识入库（切块 + embedding + 全文向量）
# 五种源：incident_resolution / manual_document / alert_rule /
#         log_pattern / k8s_event_pattern
# ============================================================

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.knowledge import KnowledgeChunk
from app.rag.embedding import embed_text

logger = get_logger("rag.ingest")


def _chunk(content: str, size: int = 800, overlap: int = 100) -> list[str]:
    """简单滑窗切块（按字符，中文友好）。"""
    if len(content) <= size:
        return [content]
    chunks, start = [], 0
    while start < len(content):
        chunks.append(content[start:start + size])
        start += size - overlap
    return chunks


async def ingest(db: AsyncSession, source_type: str, title: str, content: str,
                 source_id: str = "", metadata: dict | None = None,
                 chunk_size: int = 800, overlap: int = 100) -> int:
    """切块 → embedding → 写入 knowledge_chunks（含全文向量）。返回块数。"""
    metadata = metadata or {}
    pieces = _chunk(content, chunk_size, overlap)
    for piece in pieces:
        vec = embed_text(piece)
        chunk = KnowledgeChunk(
            source_type=source_type, source_id=source_id,
            title=title, content=piece, embedding=vec, doc_metadata=metadata,
        )
        db.add(chunk)
        await db.flush()
        # 生成全文检索向量
        await db.execute(
            text("UPDATE knowledge_chunks SET search_vector = "
                 "to_tsvector('simple', :c) WHERE id = :id"),
            {"c": piece, "id": chunk.id},
        )
    logger.info("rag.ingest.done", source_type=source_type, chunks=len(pieces))
    return len(pieces)
