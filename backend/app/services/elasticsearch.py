# ============================================================
# app/services/elasticsearch.py — ES 日志查询（支持多环境）
# ============================================================

from app.core.config import settings
from app.core.logging import get_logger
from app.services.environments import EnvironmentProfile, get_active_profile

logger = get_logger("es")

_clients: dict[str, object] = {}


def _client_key(profile: EnvironmentProfile) -> str:
    host = profile.es_host or settings.ES_HOST
    return f"{host}:{profile.es_port or settings.ES_PORT}"


def get_es_client(profile: EnvironmentProfile | None = None):
    profile = profile or get_active_profile()
    host = (profile.es_host or settings.ES_HOST or "").strip()
    if not host:
        return None
    key = _client_key(profile)
    if key in _clients:
        return _clients[key]
    try:
        from elasticsearch import AsyncElasticsearch
        port = profile.es_port or settings.ES_PORT
        client = AsyncElasticsearch(
            hosts=[f"http://{host}:{port}"],
            basic_auth=(settings.ES_USER, settings.ES_PASSWORD) if settings.ES_PASSWORD else None,
            request_timeout=15,
            max_retries=2,
            retry_on_timeout=True,
        )
        _clients[key] = client
    except Exception as exc:
        logger.warning("es.init.failed", error=str(exc))
        return None
    return _clients.get(key)


async def search_logs(
    query: str,
    index: str = "logs-*",
    size: int = 50,
    hours_back: int = 1,
    profile: EnvironmentProfile | None = None,
) -> list[dict]:
    client = get_es_client(profile)
    if client is None:
        logger.debug("es.skip", reason="no ES host")
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
    except Exception as exc:
        logger.warning("es.search.failed", error=str(exc))
        return []


async def aggregate_errors(
    index: str = "logs-*",
    hours_back: int = 1,
    profile: EnvironmentProfile | None = None,
) -> list[dict]:
    client = get_es_client(profile)
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
            "aggs": {"error_patterns": {"terms": {"field": "message.keyword", "size": 20}}},
        }
        resp = await client.search(index=index, body=body)
        return resp["aggregations"]["error_patterns"]["buckets"]
    except Exception as exc:
        logger.warning("es.aggregate.failed", error=str(exc))
        return []
