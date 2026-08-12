# ============================================================
# app/rag/retriever.py — 混合检索（向量 0.7 + 全文 0.3）+ rerank
# ============================================================

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embedding import embed_text, rerank

logger = get_logger("rag.retriever")


async def hybrid_search(db: AsyncSession, query: str,
                        affected_services: list[str] | None = None,
                        top_k: int | None = None, top_n: int | None = None) -> list[dict]:
    """混合检索：pgvector 余弦 + 全文 ts_rank，本地 rerank 精排。

    过滤：90 天内 + （可选）服务标签匹配。
    """
    top_k = top_k or settings.RAG_TOP_K
    top_n = top_n or settings.RAG_RERANK_TOP_N
    qvec = embed_text(query)
    vec_literal = "[" + ",".join(str(x) for x in qvec) + "]"

    svc_filter = ""
    params: dict = {"q": query, "qvec": vec_literal, "k": top_k}
    if affected_services:
        svc_filter = "AND (doc_metadata->'services' ?| :svcs)"
        params["svcs"] = affected_services

    sql = text(f"""
        SELECT id, source_type, title, content, doc_metadata,
               (1 - (embedding <=> (:qvec)::vector)) * 0.7
             + ts_rank(search_vector, plainto_tsquery('simple', :q)) * 0.3 AS score
        FROM knowledge_chunks
        WHERE created_at > NOW() - INTERVAL '90 days' {svc_filter}
        ORDER BY score DESC
        LIMIT :k
    """)
    try:
        rows = (await db.execute(sql, params)).mappings().all()
    except Exception as e:  # noqa: BLE001
        logger.warning("rag.search.failed", error=str(e))
        return []

    if not rows:
        return []

    # 本地 rerank 精排
    docs = [r["content"] for r in rows]
    ranked = rerank(query, docs, top_n=top_n)
    results = []
    for idx, score in ranked:
        r = rows[idx]
        results.append({
            "id": str(r["id"]), "source_type": r["source_type"],
            "title": r["title"],
            "content": r["content"][:1200],  # 压缩注入
            "metadata": r["doc_metadata"], "score": score,
        })
    return results
