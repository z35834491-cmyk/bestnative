# ============================================================
# app/services/trace_topology.py — 从 ES trace_log 还原真实调用链路
# ============================================================

from __future__ import annotations

import asyncio
import copy
import re
import time
from collections import defaultdict
from statistics import mean
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

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

# 只取拓扑/时间线需要的字段，避免拉取整条日志（logMessage 可能非常大）
_SOURCE_FIELDS = [
    "timestamp", "@timestamp", "traceId", "spanId", "serviceName", "podName",
    "podNodeName", "thread", "logLevel", "javaModule", "lineNum", "logMessage",
]


def _es_hosts() -> list[str]:
    if not settings.ES_HOST:
        return []
    host = settings.ES_HOST.strip().rstrip("/")
    if host.startswith("http://") or host.startswith("https://"):
        return [host]
    return [f"https://{host}:{settings.ES_PORT}", f"http://{host}:{settings.ES_PORT}"]


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


async def _search_trace_log(body: dict[str, Any]) -> dict[str, Any]:
    last_error = ""
    client = _get_client()
    for host in _es_hosts():
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
    text = " ".join(str(event.get(k) or "") for k in ("javaModule", "thread", "logMessage")).lower()
    if "actual sql" in text or "logic sql" in text or "jdbc" in text or "mybatis" in text or "shardingsphere" in text or "hardingphere" in text:
        return "mysql"
    if " redis" in f" {text}" or "redisson" in text or "lettuce" in text or "jedis" in text or "zset" in text:
        return "redis"
    # exchange 是交易业务高频词，不能作为 RabbitMQ 判断依据。
    if "rabbit" in text or "routingkey" in text or " queue" in f" {text}" or ".mq." in text or "mq.producer" in text or "mq.consumer" in text or "sendtomatch" in text:
        return "rabbitmq"
    return None


def _node_label(kind: str) -> str:
    return {"mysql": "MySQL", "redis": "Redis", "rabbitmq": "RabbitMQ"}.get(kind, kind)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return round(ordered[idx], 2)


def _source(hit: dict[str, Any]) -> dict[str, Any]:
    src = hit.get("_source") or {}
    message = _clean_message(str(src.get("logMessage") or ""))
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
        "durationMs": _duration_ms(message),
    }
    event["component"] = _middleware_kind(event)
    return event


def _term_or_match(field: str, value: str) -> list[dict[str, Any]]:
    return [
        {"term": {f"{field}.keyword": value}},
        {"term": {field: value}},
        {"match_phrase": {field: value}},
    ]


def _time_filter(hours: int) -> dict[str, Any]:
    safe_hours = max(1, min(hours, 168))
    return {"range": {"timestamp": {"gte": f"now-{safe_hours}h"}}}


# ---- 轻量结果缓存（单实例部署；短 TTL，合并瞬时重复请求，避免击穿 ES） ----
_cache: dict[str, tuple[float, Any]] = {}
_cache_locks: dict[str, asyncio.Lock] = {}
_TRACE_GRAPH_TTL = 20.0      # 秒
_TRACE_TIMELINE_TTL = 30.0   # 秒


async def _get_cached(key: str, ttl: float, factory) -> Any:
    """带合并锁的短 TTL 缓存：并发相同请求只真正命中 ES 一次。"""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return copy.deepcopy(hit[1])
    lock = _cache_locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] > now:
            return copy.deepcopy(hit[1])
        result = await factory()
        _cache[key] = (time.monotonic() + ttl, result)
        return copy.deepcopy(result)


async def get_trace_timeline(trace_id: str, size: int = 500) -> dict[str, Any]:
    safe_size = max(1, min(size, 2000))
    return await _get_cached(f"tl:{trace_id}:{safe_size}", _TRACE_TIMELINE_TTL, lambda: _build_trace_timeline(trace_id, safe_size))


async def _build_trace_timeline(trace_id: str, size: int) -> dict[str, Any]:
    body = {
        "size": size,
        "track_total_hits": False,
        "_source": _SOURCE_FIELDS,
        "sort": [{"timestamp": {"order": "asc", "unmapped_type": "date"}}],
        "query": {"bool": {"should": _term_or_match("traceId", trace_id), "minimum_should_match": 1}},
    }
    resp = await _search_trace_log(body)
    events = [_source(h) for h in resp.get("hits", {}).get("hits", [])]
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
        "eventCount": len(events),
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


async def get_trace_graph(service: str = "", hours: int = 1, trace_limit: int = 200, event_limit: int = 2000) -> dict[str, Any]:
    safe_hours = max(1, min(hours, 168))
    safe_trace_limit = max(1, min(trace_limit, 500))
    safe_event_limit = max(1, min(event_limit, 5000))
    key = f"tg:{service}:{safe_hours}:{safe_trace_limit}:{safe_event_limit}"
    return await _get_cached(key, _TRACE_GRAPH_TTL, lambda: _build_trace_graph(service, safe_hours, safe_trace_limit, safe_event_limit))


async def _build_trace_graph(service: str, hours: int, trace_limit: int, event_limit: int) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [_time_filter(hours), {"exists": {"field": "traceId"}}, {"exists": {"field": "serviceName"}}]
    if service:
        filters.append({"bool": {"should": _term_or_match("serviceName", service), "minimum_should_match": 1}})

    trace_body = {
        "size": 0,
        "track_total_hits": False,
        "query": {"bool": {"filter": filters}},
        "aggs": {"traces": {"terms": {"field": "traceId.keyword", "size": trace_limit, "order": {"last_seen": "desc"}}, "aggs": {"last_seen": {"max": {"field": "timestamp"}}}}},
    }
    trace_resp = await _search_trace_log(trace_body)
    buckets = trace_resp.get("aggregations", {}).get("traces", {}).get("buckets", [])
    trace_ids = [b.get("key") for b in buckets if b.get("key")]
    if not trace_ids:
        return {"nodes": [], "edges": [], "traces": [], "source": "es:trace_log", "hours": hours, "service": service}

    event_body = {
        "size": event_limit,
        "track_total_hits": False,
        "_source": _SOURCE_FIELDS,
        "sort": [{"traceId.keyword": {"order": "asc"}}, {"timestamp": {"order": "asc", "unmapped_type": "date"}}],
        "query": {"bool": {"filter": [{"terms": {"traceId.keyword": trace_ids}}]}},
    }
    event_resp = await _search_trace_log(event_body)
    events = [_source(h) for h in event_resp.get("hits", {}).get("hits", [])]

    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event["traceId"]:
            by_trace[event["traceId"]].append(event)

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    edge_latencies: dict[tuple[str, str], list[float]] = defaultdict(list)
    traces: list[dict[str, Any]] = []

    for trace_id, items in by_trace.items():
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
            edge["lastTraceId"] = trace_id
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
            "traceId": trace_id,
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
    return {
        "nodes": list(nodes.values()),
        "edges": sorted(edges.values(), key=lambda x: x["traceCount"], reverse=True),
        "traces": traces[:trace_limit],
        "source": "es:trace_log",
        "hours": hours,
        "service": service,
    }
