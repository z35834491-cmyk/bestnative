# ============================================================
# app/services/elasticsearch.py — ES 日志查询封装
# ============================================================

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("es")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not settings.ES_HOST:
        return None
    try:
        from elasticsearch import AsyncElasticsearch
        _client = AsyncElasticsearch(
            hosts=[f"http://{settings.ES_HOST}:{settings.ES_PORT}"],
            basic_auth=(settings.ES_USER, settings.ES_PASSWORD) if settings.ES_PASSWORD else None,
            request_timeout=15,
            max_retries=2,
            retry_on_timeout=True,
        )
    except Exception as e:
        logger.warning("es.init.failed", error=str(e))
        _client = None
    return _client


async def search_logs(query: str, index: str = "logs-*", size: int = 50,
                      hours_back: int = 1) -> list[dict]:
    """搜索 ES 日志（全文 + 时间范围）。"""
    client = _get_client()
    if client is None:
        logger.debug("es.skip", reason="no ES_HOST configured")
        return []
    try:
        body = {
            "query": {
                "bool": {
                    "must": [{"query_string": {"query": query}}],
                    "filter": [{"range": {"@timestamp": {"gte": f"now-{hours_back}h"}}}],
                }
            },
            "size": size,
            "sort": [{"@timestamp": {"order": "desc"}}],
        }
        resp = await client.search(index=index, body=body)
        return [h["_source"] for h in resp["hits"]["hits"]]
    except Exception as e:
        logger.warning("es.search.failed", error=str(e))
        return []


async def aggregate_errors(index: str = "logs-*", hours_back: int = 1) -> list[dict]:
    """聚合最近一段时间的错误日志模式（Agent 诊断用）。"""
    client = _get_client()
    if client is None:
        return []
    try:
        body = {
            "query": {
                "bool": {
                    "filter": [
                        {"range": {"@timestamp": {"gte": f"now-{hours_back}h"}}},
                        {"term": {"level": "ERROR"}},
                    ]
                }
            },
            "size": 0,
            "aggs": {
                "error_patterns": {
                    "terms": {"field": "message.keyword", "size": 20}
                }
            },
        }
        resp = await client.search(index=index, body=body)
        return resp["aggregations"]["error_patterns"]["buckets"]
    except Exception as e:
        logger.warning("es.aggregate.failed", error=str(e))
        return []
