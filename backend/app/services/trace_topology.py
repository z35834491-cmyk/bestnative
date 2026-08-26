# ============================================================
# app/services/trace_topology.py — 从 ES trace_log 还原真实调用链路
# ============================================================

from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from statistics import mean
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.environments import EnvironmentProfile, get_active_profile

logger = get_logger("trace_topology")

_TRACE_INDEX = "trace_log"
_SENSITIVE_PATTERNS = [
    re.compile(r"(apiKey=)[^ |]+", re.I),
    re.compile(r"((?:password|token|secret)\s*[:=]\s*)[^, |}]+", re.I),
]
_DURATION_PATTERNS = [
    re.compile(r"耗时\(?\s*(\d+(?:\.\d+)?)\s*ms\)?", re.I),
    re.compile(r"(?:duration|cost|elapsed|latency)\s*[:=]\s*(\d+(?:\.\d+)?)\s*ms", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*毫秒", re.I),
]

# 拓扑图构建：不拉 logMessage（体积大，图聚合不需要完整日志）
_GRAPH_SOURCE_FIELDS = [
    "timestamp", "@timestamp", "traceId", "spanId", "serviceName", "podName",
    "podNodeName", "thread", "logLevel", "javaModule", "lineNum",
]
# 时间线详情：含 logMessage，但在 _source() 中截断
_TIMELINE_SOURCE_FIELDS = _GRAPH_SOURCE_FIELDS + ["logMessage"]
# 兼容旧引用
_SOURCE_FIELDS = _TIMELINE_SOURCE_FIELDS

_MAX_LOG_MESSAGE_LEN = 2000


def _es_hosts(profile: EnvironmentProfile | None = None) -> list[str]:
    profile = profile or get_active_profile()
    host_raw = (profile.es_host or settings.ES_HOST or "").strip()
    if not host_raw:
        return []
    host = host_raw.rstrip("/")
    port = profile.es_port or settings.ES_PORT
    if host.startswith("http://") or host.startswith("https://"):
        return [host]
    return [f"https://{host}:{port}", f"http://{host}:{port}"]


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """复用一个常驻 httpx.AsyncClient，复用连接池，避免每次请求重建连接。"""
    global _client
    if _client is None or _client.is_closed:
        auth = (settings.ES_USER, settings.ES_PASSWORD) if settings.ES_PASSWORD else None
        # 连接超时短、读取超时长：ES 不可达时快速失败（不再卡 25s×2 主机），
        # 但可达时慢查询仍能拿到结果（读超时 30s，不低于原先 25s）。
        _client = httpx.AsyncClient(
            verify=False,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
            auth=auth,
        )
    return _client


async def _search_trace_log(body: dict[str, Any], profile: EnvironmentProfile | None = None) -> dict[str, Any]:
    last_error = ""
    client = _get_client()
    for host in _es_hosts(profile):
        try:
            resp = await client.post(f"{host}/{_TRACE_INDEX}/_search", json=body)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {str(exc)[:180]}"
            logger.warning("trace_log.search.failed", host=host.split("://", 1)[0], error=last_error)
    raise RuntimeError(last_error or "ES 未配置")


def _clean_message(message: str) -> str:
    text = message or ""
    for pat in _SENSITIVE_PATTERNS:
        text = pat.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return text


def _duration_ms(text: str) -> float | None:
    for pattern in _DURATION_PATTERNS:
        match = pattern.search(text or "")
        if match:
            try:
                return round(float(match.group(1)), 2)
            except ValueError:
                return None
    return None


def _middleware_kind(event: dict[str, Any]) -> str | None:
    module = str(event.get("javaModule") or "").lower()
    thread = str(event.get("thread") or "").lower()
    message = str(event.get("logMessage") or "").lower()
    text = f"{module} {thread} {message}"

    # javaModule / 线程名优先（比 logMessage 更稳定）
    if any(k in module for k in (
        "jdbc", "mybatis", "mysql", "mariadb", "druid", "hikari", "shardingsphere",
        "hibernate.orm", "jpa.", "datasource", "sql.", "mapper.",
    )):
        return "mysql"
    if any(k in module for k in ("redisson", "lettuce", "jedis", "redis", "spring.data.redis", "io.lettuce")):
        return "redis"
    if any(k in module for k in ("rabbit", "amqp", "spring.amqp", "rocketmq", "kafka")):
        return "rabbitmq"
    if any(k in module for k in ("elasticsearch", "co.elastic", "rest.client", "opensearch")):
        return "elasticsearch"

    if any(k in text for k in (
        "actual sql", "logic sql", "jdbc", "mybatis", "shardingsphere", "hikari",
        "preparedstatement", "executing sql", "==>  pre", "==> parameters",
    )):
        return "mysql"
    if any(k in text for k in (
        " redis", "redis://", "redisson", "lettuce", "jedis", "redis template",
        "get key", "set key", "cache hit", "cache miss", "zset", "hset", "hmget",
    )):
        return "redis"
    if any(k in text for k in (
        "rabbit", "routingkey", "routing key", " queue", ".mq.", "mq.producer",
        "mq.consumer", "sendtomatch", "amqp", "basic.publish", "basic.consume",
    )):
        return "rabbitmq"
    if any(k in text for k in (
        "elasticsearch", "opensearch", "_search", "trace_log", "index not found",
        ":9200", "resthighlevelclient",
    )):
        return "elasticsearch"
    return None


def _source(hit: dict[str, Any], *, include_message: bool = True) -> dict[str, Any]:
    src = hit.get("_source") or {}
    raw_message = str(src.get("logMessage") or "") if include_message else ""
    if include_message and len(raw_message) > _MAX_LOG_MESSAGE_LEN:
        raw_message = raw_message[:_MAX_LOG_MESSAGE_LEN] + "…[truncated]"
    message = _clean_message(raw_message) if include_message else ""
    event = {
        "timestamp": src.get("timestamp") or src.get("@timestamp") or "",
        "traceId": src.get("traceId") or "",
        "spanId": src.get("spanId") or "",
        "serviceName": src.get("serviceName") or "unknown",
        "podName": src.get("podName") or "",
        "podNodeName": src.get("podNodeName") or "",
        "thread": src.get("thread") or "",
        "logLevel": src.get("logLevel") or "INFO",
        "javaModule": src.get("javaModule") or "",
        "lineNum": src.get("lineNum") or "",
        "logMessage": message,
        "durationMs": _duration_ms(message) if include_message else None,
    }
    event["component"] = _middleware_kind(event)
    return event


def _node_label(kind: str) -> str:
    return {
        "mysql": "MySQL",
        "redis": "Redis",
        "rabbitmq": "RabbitMQ",
        "elasticsearch": "Elasticsearch",
        "postgresql": "PostgreSQL",
        "mongodb": "MongoDB",
    }.get(kind, kind)


def _trim_trace_events(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """保留含中间件信号的日志，避免 events_per_trace 截断后只剩 MQ 类日志。"""
    if len(items) <= limit:
        return items
    important = [e for e in items if e.get("component")]
    rest = [e for e in items if not e.get("component")]
    if len(important) >= limit:
        return important[:limit]
    return important + rest[: limit - len(important)]


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return round(ordered[idx], 2)


def _term_or_match(field: str, value: str) -> list[dict[str, Any]]:
    return [
        {"term": {f"{field}.keyword": value}},
        {"term": {field: value}},
        {"match_phrase": {field: value}},
    ]


def _time_filter(hours: int) -> dict[str, Any]:
    safe_hours = max(1, min(hours, 168))
    return {"range": {"timestamp": {"gte": f"now-{safe_hours}h"}}}


# ---- 轻量结果缓存（单实例；有容量上限，避免内存无限增长） ----
_cache: dict[str, tuple[float, Any]] = {}
_cache_locks: dict[str, asyncio.Lock] = {}
_CACHE_MAX = 64
_TRACE_GRAPH_TTL = 60.0
_TRACE_TIMELINE_TTL = 45.0


def _cache_set(key: str, ttl: float, value: Any) -> None:
    if len(_cache) >= _CACHE_MAX:
        oldest_key = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest_key, None)
        _cache_locks.pop(oldest_key, None)
    _cache[key] = (time.monotonic() + ttl, value)


async def _get_cached(key: str, ttl: float, factory) -> Any:
    """带合并锁的短 TTL 缓存：内存 + Redis 双层。"""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    from app.services.redis_cache import cache_get, cache_set as redis_set
    redis_hit = await cache_get(key)
    if redis_hit is not None:
        _cache_set(key, ttl, redis_hit)
        return redis_hit
    lock = _cache_locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
        result = await factory()
        _cache_set(key, ttl, result)
        await redis_set(key, result, int(ttl))
        return result


async def get_trace_timeline(trace_id: str, size: int = 500, offset: int = 0) -> dict[str, Any]:
    safe_size = max(1, min(size, 500))
    safe_offset = max(0, min(offset, 5000))
    return await _get_cached(
        f"tl:{trace_id}:{safe_offset}:{safe_size}",
        _TRACE_TIMELINE_TTL,
        lambda: _build_trace_timeline(trace_id, safe_size, safe_offset),
    )


async def _build_trace_timeline(trace_id: str, size: int, offset: int = 0) -> dict[str, Any]:
    body = {
        "size": size,
        "from": offset,
        "track_total_hits": offset == 0,
        "_source": _TIMELINE_SOURCE_FIELDS,
        "sort": [{"timestamp": {"order": "asc", "unmapped_type": "date"}}],
        "query": {"bool": {"should": _term_or_match("traceId", trace_id), "minimum_should_match": 1}},
    }
    resp = await _search_trace_log(body)
    hits = resp.get("hits", {})
    events = [_source(h, include_message=True) for h in hits.get("hits", [])]
    total = hits.get("total", {})
    total_count = total.get("value", len(events)) if isinstance(total, dict) else len(events)
    services: list[str] = []
    components: list[str] = []
    durations = [e["durationMs"] for e in events if e.get("durationMs") is not None]
    for e in events:
        svc = e["serviceName"]
        if svc not in services:
            services.append(svc)
        comp = e.get("component")
        if comp and comp not in components:
            components.append(comp)
    return {
        "traceId": trace_id,
        "services": services,
        "components": components,
        "events": events,
        "eventCount": total_count,
        "offset": offset,
        "pageSize": size,
        "hasMore": offset + len(events) < total_count,
        "hasError": any(str(e["logLevel"]).upper() in {"ERROR", "WARN"} for e in events),
        "maxDurationMs": max(durations) if durations else None,
    }


def _add_node(nodes: dict[str, dict[str, Any]], node_id: str, name: str, node_type: str, level: str, timestamp: str) -> dict[str, Any]:
    node = nodes.setdefault(node_id, {
        "id": node_id,
        "name": name,
        "type": node_type,
        "namespace": "trace_log",
        "health": "healthy",
        "traceCount": 0,
        "errorCount": 0,
        "lastSeen": "",
    })
    node["lastSeen"] = max(str(node.get("lastSeen") or ""), str(timestamp or ""))
    if level in {"ERROR", "WARN"}:
        node["errorCount"] += 1
    return node


async def get_trace_graph(
    service: str = "",
    hours: int = 1,
    trace_limit: int = 80,
    events_per_trace: int = 30,
    trace_id: str = "",
    profile: EnvironmentProfile | None = None,
) -> dict[str, Any]:
    profile = profile or get_active_profile()
    tid = (trace_id or "").strip()
    if tid:
        key = f"tg:tid:{tid}:{profile.id}"
        return await _get_cached(key, _TRACE_GRAPH_TTL, lambda: _build_single_trace_graph(tid, profile))

    safe_hours = max(1, min(hours, 168))
    safe_trace_limit = max(1, min(trace_limit, 200))
    safe_events_per_trace = max(5, min(events_per_trace, 80))
    key = f"tg:{profile.id}:{service}:{safe_hours}:{safe_trace_limit}:{safe_events_per_trace}"
    return await _get_cached(
        key,
        _TRACE_GRAPH_TTL,
        lambda: _build_trace_graph(service, safe_hours, safe_trace_limit, safe_events_per_trace, profile),
    )


async def _build_single_trace_graph(trace_id: str, profile: EnvironmentProfile | None = None) -> dict[str, Any]:
    body = {
        "size": 500,
        "track_total_hits": False,
        "_source": {"includes": _TIMELINE_SOURCE_FIELDS},
        "sort": [{"timestamp": {"order": "asc", "unmapped_type": "date"}}],
        "query": {"bool": {"should": _term_or_match("traceId", trace_id), "minimum_should_match": 1}},
    }
    resp = await _search_trace_log(body, profile)
    items = [_source(h, include_message=True) for h in resp.get("hits", {}).get("hits", [])]
    if not items:
        return {"nodes": [], "edges": [], "traces": [], "source": "es:trace_log", "hours": 0, "service": "", "traceId": trace_id}
    return _graph_from_by_trace({trace_id: items}, trace_limit=1, hours=0, service="", trace_id=trace_id)


def _graph_from_by_trace(
    by_trace: dict[str, list[dict[str, Any]]],
    *,
    trace_limit: int,
    hours: int,
    service: str,
    trace_id: str = "",
) -> dict[str, Any]:
    if not by_trace:
        return {"nodes": [], "edges": [], "traces": [], "source": "es:trace_log", "hours": hours, "service": service}

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    edge_latencies: dict[tuple[str, str], list[float]] = defaultdict(list)
    traces: list[dict[str, Any]] = []

    for tid, items in by_trace.items():
        sequence: list[str] = []
        services: list[str] = []
        components: list[str] = []
        has_error = False
        trace_durations: list[float] = []
        last_service = ""

        for item in items:
            svc = item["serviceName"] or "unknown"
            level = str(item["logLevel"]).upper()
            has_error = has_error or level in {"ERROR", "WARN"}
            duration = item.get("durationMs")
            if duration is not None:
                trace_durations.append(duration)

            node = _add_node(nodes, svc, svc, "service", level, item["timestamp"])
            if svc not in services:
                services.append(svc)
                node["traceCount"] += 1
            if not sequence or sequence[-1] != svc:
                sequence.append(svc)
            last_service = svc

            comp = item.get("component")
            if comp:
                mid_id = f"middleware:{comp}"
                mid = _add_node(nodes, mid_id, _node_label(comp), "middleware", level, item["timestamp"])
                mid["component"] = comp
                if comp not in components:
                    components.append(comp)
                    mid["traceCount"] += 1
                if sequence[-1] != mid_id:
                    sequence.append(mid_id)
                if duration is not None and last_service:
                    edge_latencies[(last_service, mid_id)].append(duration)

        seen_edge_keys: set[tuple[str, str]] = set()
        for a, b in zip(sequence, sequence[1:]):
            if a == b or (a, b) in seen_edge_keys:
                continue
            seen_edge_keys.add((a, b))
            edge = edges.setdefault((a, b), {"from": a, "to": b, "source": a, "target": b, "detectedBy": "trace", "traceCount": 0, "errorCount": 0, "lastTraceId": "", "lastSeen": "", "health": "healthy"})
            edge["traceCount"] += 1
            edge["lastTraceId"] = tid
            edge["lastSeen"] = max(str(edge.get("lastSeen") or ""), str(items[-1].get("timestamp") or ""))
            if has_error:
                edge["errorCount"] += 1
                edge["health"] = "degraded"

        # 业务服务之间没有 span duration 字段时，用目标服务 afterCompletion 耗时作为边延迟近似。
        # O(n)：记录"上一个与当前不同的服务"，等价于原先逐项回查，避免 trace 内 O(n²) 扫描。
        current_svc = ""
        prev_svc = ""
        for item in items:
            svc = item["serviceName"] or "unknown"
            duration = item.get("durationMs")
            if svc != current_svc:
                prev_svc, current_svc = current_svc, svc
            if duration is not None and prev_svc and prev_svc != svc and (prev_svc, svc) in edges:
                edge_latencies[(prev_svc, svc)].append(duration)

        traces.append({
            "traceId": tid,
            "services": services,
            "components": components,
            "eventCount": len(items),
            "hasError": has_error,
            "firstSeen": items[0].get("timestamp") if items else "",
            "lastSeen": items[-1].get("timestamp") if items else "",
            "maxDurationMs": max(trace_durations) if trace_durations else None,
        })

    for key, edge in edges.items():
        values = edge_latencies.get(key, [])
        if values:
            edge["avgLatencyMs"] = round(mean(values), 2)
            edge["p95LatencyMs"] = _percentile(values, 0.95)
            edge["latencySamples"] = len(values)
    for node in nodes.values():
        if node["errorCount"]:
            node["health"] = "degraded"

    traces.sort(key=lambda x: str(x.get("lastSeen") or ""), reverse=True)
    result = {
        "nodes": list(nodes.values()),
        "edges": sorted(edges.values(), key=lambda x: x["traceCount"], reverse=True),
        "traces": traces[:trace_limit],
        "source": "es:trace_log",
        "hours": hours,
        "service": service,
    }
    if trace_id:
        result["traceId"] = trace_id
    return result


async def _build_trace_graph(
    service: str,
    hours: int,
    trace_limit: int,
    events_per_trace: int,
    profile: EnvironmentProfile | None = None,
) -> dict[str, Any]:
    # 第一步：按入口服务筛 traceId（只用于发现链路，不能用于拉事件）
    discover_filters: list[dict[str, Any]] = [
        _time_filter(hours),
        {"exists": {"field": "traceId"}},
        {"exists": {"field": "serviceName"}},
    ]
    if service:
        discover_filters.append({"bool": {"should": _term_or_match("serviceName", service), "minimum_should_match": 1}})

    trace_body = {
        "size": 0,
        "track_total_hits": False,
        "query": {"bool": {"filter": discover_filters}},
        "aggs": {
            "traces": {
                "terms": {
                    "field": "traceId.keyword",
                    "size": trace_limit,
                    "order": {"last_seen": "desc"},
                },
                "aggs": {"last_seen": {"max": {"field": "timestamp"}}},
            }
        },
    }
    trace_resp = await _search_trace_log(trace_body, profile)
    buckets = trace_resp.get("aggregations", {}).get("traces", {}).get("buckets", [])
    trace_ids = [str(b.get("key")) for b in buckets if b.get("key")]
    if not trace_ids:
        return {"nodes": [], "edges": [], "traces": [], "source": "es:trace_log", "hours": hours, "service": service}

    # 第二步：按 traceId 拉全链路事件（不再带 service 过滤，否则只剩入口服务日志）
    fetch_size = min(trace_limit * events_per_trace, 4000)
    event_body = {
        "size": fetch_size,
        "track_total_hits": False,
        "_source": {"includes": _TIMELINE_SOURCE_FIELDS},
        "sort": [
            {"traceId.keyword": {"order": "asc"}},
            {"timestamp": {"order": "asc", "unmapped_type": "date"}},
        ],
        "query": {"bool": {"filter": [{"terms": {"traceId.keyword": trace_ids}}]}},
    }
    event_resp = await _search_trace_log(event_body, profile)
    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hit in event_resp.get("hits", {}).get("hits", []):
        event = _source(hit, include_message=True)
        tid = event.get("traceId")
        if tid:
            by_trace[str(tid)].append(event)

    # 每个 trace 保留 N 条：优先含 MySQL/Redis/MQ 等中间件信号的日志
    for tid in list(by_trace.keys()):
        if len(by_trace[tid]) > events_per_trace:
            by_trace[tid] = _trim_trace_events(by_trace[tid], events_per_trace)

    return _graph_from_by_trace(by_trace, trace_limit=trace_limit, hours=hours, service=service)
