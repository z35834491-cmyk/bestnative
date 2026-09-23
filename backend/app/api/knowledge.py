# ============================================================
# app/api/knowledge.py — 知识库检索
# ============================================================

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_user
from app.models.auth import User
from app.rag.retriever import hybrid_search

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeSearchRequest(BaseModel):
    query: str
    services: list[str] = Field(default_factory=list)
    top_k: int = 10


@router.post("/search")
async def search_knowledge(body: KnowledgeSearchRequest, db: AsyncSession = Depends(get_db),
                           _user: User = Depends(require_user)):
    results = await hybrid_search(db, body.query, affected_services=body.services or None, top_k=body.top_k)
    return {"results": results, "count": len(results)}


@router.get("/search")
async def search_knowledge_get(q: str = Query(..., min_length=1), service: str = "",
                               db: AsyncSession = Depends(get_db),
                               _user: User = Depends(require_user)):
    services = [service] if service else None
    results = await hybrid_search(db, q, affected_services=services)
    return {"results": results, "count": len(results)}
