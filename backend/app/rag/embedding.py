# ============================================================
# app/rag/embedding.py — 本地 embedding + rerank（零 API 费）
# bge-small-zh-v1.5 (512维) / bge-reranker-v2-m3
# 懒加载模型，避免启动即占内存
# ============================================================

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("rag.embedding")

_embedder = None
_reranker = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        logger.info("rag.embedder.loading", model=settings.EMBEDDING_MODEL)
        _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedder


def embed_text(text: str) -> list[float]:
    """单条文本 → 向量。"""
    vec = get_embedder().encode(text, normalize_embeddings=True)
    return vec.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    vecs = get_embedder().encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vecs]


def get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        logger.info("rag.reranker.loading", model=settings.RERANK_MODEL)
        _reranker = CrossEncoder(settings.RERANK_MODEL)
    return _reranker


def rerank(query: str, docs: list[str], top_n: int = 3) -> list[tuple[int, float]]:
    """返回 [(doc_index, score)] 按分数降序，取 top_n。"""
    if not docs:
        return []
    pairs = [[query, d] for d in docs]
    scores = get_reranker().predict(pairs)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return [(i, float(s)) for i, s in ranked[:top_n]]
