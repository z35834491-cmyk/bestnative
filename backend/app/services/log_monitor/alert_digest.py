# ============================================================
# app/services/log_monitor/alert_digest.py — 日志告警摘要（Slack 一眼可读）
# ============================================================

from __future__ import annotations

import base64
import re

from app.services.log_monitor.log_keyword_match import (
    extract_log_level,
    is_config_noise_line,
    is_digest_worthy_line,
)

SLACK_DIGEST_MAX = 2200
DEFAULT_TAIL_LINES = 200

_ANSI = re.compile(r"\x1b\[[0-9;]*m|\x1b\].*?(?:\x07|\x1b\\)")
_TS_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?\s*\|\s*")
_LEVEL_PREFIX = re.compile(r"^(ERROR|WARN|INFO|DEBUG|TRACE|FATAL)\s+\d+\s*\|\s*", re.I)
_ISO_TS = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\s+"
)
_WRAPPER_EXCEPTIONS = frozenset({
    "InvocationTargetException",
    "CompletionException",
    "UndeclaredThrowableException",
    "ExecutionException",
    "ReflectiveOperationException",
    "ServletException",
})
_JAVA_FRAME = re.compile(r"^[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$][\w$]*)+\([A-Za-z0-9_$.]+:\d+\)$")
_ACCESS_LOG_NOISE = (
    "ApiAccessLogInterceptor",
    "preHandle",
    "afterCompletion",
    "afterCompl",
    "开始请求 URL",
    "DispatcherServlet",
    "Completed initialization",
)

_SECRET_VALUE = re.compile(r"^[A-Za-z0-9_\-+/=.]{8,}$")
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(API\s*key\s*不存在\s*:\s*)(\S+)", re.I),
    re.compile(r"((?:api[_-]?key|access[_-]?key|secret[_-]?key|auth[_-]?token)\s*[:=]\s*)(\S+)", re.I),
    re.compile(r"(Bearer\s+)(\S+)", re.I),
    re.compile(r"((?:token|password|passwd|pwd)\s*[:=]\s*)(\S+)", re.I),
]
# JSON 内敏感字段："apiKey":"ck4D..."
_JSON_SECRET_FIELD = re.compile(
    r'("(?:apiKey|api_key|accessKey|access_key|secretKey|secret_key|authToken|auth_token|token|password)"'
    r'\s*:\s*")([^"]{8,})(")',
    re.I,
)


def _redact_json_secrets(text: str) -> str:
    return _JSON_SECRET_FIELD.sub(
        lambda m: m.group(1) + _encode_secret(m.group(2)) + m.group(3),
        text,
    )


def _encode_secret(value: str) -> str:
    token = (value or "").strip().rstrip(".,;)]}\"'")
    if not token or not _SECRET_VALUE.match(token):
        return value
    encoded = base64.b64encode(token.encode("utf-8")).decode("ascii")
    return f"b64:{encoded}"


def redact_secrets_for_display(text: str) -> str:
    """告警/Slack 展示用：将 API key 等敏感值替换为 b64:...，需要时可 base64 解码。"""
    if not text:
        return text
    out = text
    out = _redact_json_secrets(out)
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(1) + _encode_secret(m.group(2)), out)
    return out


def _ensure_text(raw: str | bytes | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    text = str(raw)
    # 误把 bytes 做了 str() 的情况：b'...'
    if len(text) > 3 and text[0] == "b" and text[1] in ("'", '"'):
        try:
            val = ast_literal_bytes(text)
            if isinstance(val, bytes):
                return val.decode("utf-8", errors="replace")
        except Exception:
            pass
    return text


def ast_literal_bytes(text: str) -> bytes | None:
    import ast
    node = ast.literal_eval(text)
    return node if isinstance(node, (bytes, str)) else None


def clean_log_line(line: str | bytes) -> str:
    return _clean_log_line(line)


def _clean_log_line(line: str | bytes) -> str:
    s = _ensure_text(line).strip()
    s = _ANSI.sub("", s)
    s = s.replace("\\x1b[", "\x1b[")  # 双重转义
    s = _ANSI.sub("", s)
    s = _ISO_TS.sub("", s)
    s = _TS_PREFIX.sub("", s)
    s = _LEVEL_PREFIX.sub("", s)
    # Java 多段 pipe：取最后一段业务消息
    if "|" in s:
        parts = [p.strip() for p in s.split("|") if p.strip()]
        if parts:
            s = parts[-1]
    s = re.sub(r"^\[[^\]]+\]\s*", "", s)
    return s.strip()


def _log_level(raw_line: str | bytes) -> str:
    return extract_log_level(_ensure_text(raw_line)) or "INFO"


def _is_noise_line(clean: str) -> bool:
    if not clean or len(clean) < 4:
        return True
    if is_config_noise_line(clean):
        return True
    return any(n in clean for n in _ACCESS_LOG_NOISE)


def _is_stack_line(s: str) -> bool:
    t = s.strip()
    return (
        t.startswith("at ")
        or t.startswith("Caused by")
        or t.startswith("Suppressed:")
        or bool(re.match(r"^[a-zA-Z_$][\w$.]*\([^)]+\)$", t))
    )


def _is_errorish(raw_line: str, clean: str) -> bool:
    if is_config_noise_line(clean):
        return False
    level = _log_level(raw_line)
    if level in ("ERROR", "FATAL", "WARN"):
        return True
    return is_digest_worthy_line(clean)


def extract_alert_line(alert_msg: str) -> str:
    msg = (alert_msg or "").strip()
    if "| Last:" in msg:
        return msg.split("| Last:", 1)[1].strip()
    if msg.startswith("[IMMEDIATE]"):
        return msg[len("[IMMEDIATE]"):].strip()
    if msg.startswith("[THRESHOLD"):
        return msg
    return msg


def _meaningful_message(msg: str | None) -> bool:
    if not msg:
        return False
    t = msg.strip().lower()
    return t not in ("", "null", "none", "n/a", "-", "undefined")


def _parse_exception_line(clean: str) -> tuple[str, str, str] | None:
    """解析异常行 → (kind, class_name, message)。kind: caused_by | primary | spring."""
    t = clean.strip()
    if not t:
        return None

    m = re.match(r"^Caused by:\s*(.+)$", t, re.I)
    if m:
        body = m.group(1).strip()
        m2 = re.match(r"^([\w.$]+(?:Exception|Error))\s*:\s*(.*)$", body)
        if m2:
            cls = m2.group(1).split(".")[-1]
            return ("caused_by", cls, m2.group(2).strip())
        return ("caused_by", body.split(":")[0].split(".")[-1], body.split(":", 1)[-1].strip() if ":" in body else "")

    m = re.match(r"^Exception\s*:\s*(.+)$", t, re.I)
    if m:
        return ("spring", "Exception", m.group(1).strip())

    m = re.match(r"^([\w.$]+(?:Exception|Error))\s*:\s*(.*)$", t)
    if m:
        return ("primary", m.group(1).split(".")[-1], m.group(2).strip())

    if re.search(r"nested exception is ", t, re.I):
        m = re.search(r"nested exception is ([\w.$]+(?:Exception|Error))\s*:\s*(.*)", t, re.I)
        if m:
            return ("caused_by", m.group(1).split(".")[-1], m.group(2).strip())

    return None


def _score_exception(clean: str) -> int:
    parsed = _parse_exception_line(clean)
    if not parsed:
        return -1
    _kind, cls, msg = parsed
    score = 0
    if _kind == "caused_by":
        score += 5
    if _kind == "spring":
        score += 15
    if cls in _WRAPPER_EXCEPTIONS:
        score -= 60
    if _meaningful_message(msg):
        score += 25 + min(len(msg), 80)
        if re.search(r"[\u4e00-\u9fff]", msg):
            score += 20
    else:
        score -= 35
    return score


def _find_hint_index(parsed: list[tuple[str, str, str]], hint_line: str | None, hint_clean: str) -> int:
    if not parsed:
        return -1
    if hint_clean and not is_config_noise_line(hint_clean):
        idx = next((i for i, (_, c, _) in enumerate(parsed) if hint_clean in c or c in hint_clean), -1)
        if idx >= 0:
            return idx
    if hint_line:
        raw_hint = hint_line.strip()
        idx = next((i for i, (r, _, _) in enumerate(parsed) if raw_hint in r or r.strip() in raw_hint), -1)
        if idx >= 0:
            return idx
    return -1


def _extract_error_block(
    parsed: list[tuple[str, str, str]],
    center_idx: int,
    *,
    back: int = 20,
    forward: int = 80,
) -> list[tuple[str, str, str]]:
    if center_idx < 0:
        return parsed[-120:] if len(parsed) > 120 else parsed
    start = max(0, center_idx - back)
    end = min(len(parsed), center_idx + forward)
    return parsed[start:end]


def _collect_stack_lines(block: list[tuple[str, str, str]], max_frames: int = 8) -> list[str]:
    frames: list[str] = []
    seen: set[str] = set()
    for _, c, _ in block:
        t = c.strip()
        if t.startswith("at "):
            frame = t[:180]
        elif _JAVA_FRAME.match(t):
            frame = f"at {t}"[:180]
        elif t.startswith("... ") and "more" in t:
            continue
        else:
            continue
        if frame not in seen:
            seen.add(frame)
            frames.append(frame)
    if len(frames) > max_frames:
        frames = frames[:3] + ["    …"] + frames[-(max_frames - 3):]
    return frames


def _format_exception_display(clean: str) -> str:
    parsed = _parse_exception_line(clean)
    if not parsed:
        return clean.strip()[:500]
    kind, cls, msg = parsed
    if kind == "spring":
        return f"Exception: {msg}"[:500]
    if _meaningful_message(msg):
        return f"{cls}: {msg}"[:500]
    return clean.strip()[:500]


def _pick_root_and_chain(block: list[tuple[str, str, str]]) -> tuple[str, list[str]]:
    """返回 (根因行, 异常链)。跳过 wrapper + null 消息。"""
    candidates: list[tuple[int, str]] = []
    chain: list[str] = []

    for _, c, _ in block:
        if c.strip().startswith("-") and set(c.strip()) <= {"-"}:
            continue
        parsed = _parse_exception_line(c)
        if not parsed:
            continue
        _kind, cls, msg = parsed
        display = c.strip()[:500]
        if _meaningful_message(msg) or cls not in _WRAPPER_EXCEPTIONS:
            if display not in chain:
                chain.append(display)
        score = _score_exception(c)
        if score >= 0:
            candidates.append((score, display))

    if not candidates:
        # 回退：任意含 Exception/Error 的非 stack 行
        for _, c, lv in block:
            if _is_stack_line(c) or _is_noise_line(c):
                continue
            if lv in ("ERROR", "FATAL") or is_digest_worthy_line(c):
                candidates.append((10, c.strip()[:500]))

    if not candidates:
        return "", []

    candidates.sort(key=lambda x: x[0], reverse=True)
    root = _format_exception_display(candidates[0][1])

    # 异常链：保留有意义的几层，去掉与根因重复
    meaningful_chain: list[str] = []
    for ln in chain:
        if _score_exception(ln) < 0:
            continue
        formatted = _format_exception_display(ln)
        if formatted != root and formatted not in meaningful_chain:
            meaningful_chain.append(formatted)
    return root, meaningful_chain[:4]


def summarize_error_log(
    raw: str | bytes,
    *,
    hint_line: str | None = None,
    max_stack: int = 8,
    max_chars: int = SLACK_DIGEST_MAX,
) -> str:
    """从完整日志中提取根因 + 异常链 + 堆栈；跳过 wrapper/null 与访问日志噪声。"""
    text = _ensure_text(raw)
    if not text.strip():
        return ""

    raw_lines = [l for l in text.splitlines() if l and l.strip() and not re.match(r"^-{10,}$", l.strip())]
    parsed: list[tuple[str, str, str]] = []
    for raw_line in raw_lines:
        clean = _clean_log_line(raw_line)
        if clean:
            parsed.append((raw_line, clean, _log_level(raw_line)))

    if not parsed and hint_line:
        clean_hint = _clean_log_line(hint_line)
        if clean_hint and not is_config_noise_line(clean_hint):
            return redact_secrets_for_display(f"*根因*\n{clean_hint[:500]}")
        return ""

    hint_clean = _clean_log_line(hint_line) if hint_line else ""
    hint_idx = _find_hint_index(parsed, hint_line, hint_clean)
    block = _extract_error_block(parsed, hint_idx)

    root, chain = _pick_root_and_chain(block)
    if not root and hint_clean and not _is_noise_line(hint_clean):
        root = hint_clean[:500]

    stack = _collect_stack_lines(block)

    parts: list[str] = []
    if root:
        parts.append(f"*根因*\n{root[:600]}")
    if chain:
        parts.append("*异常链*\n" + "\n".join(f"• {ln[:400]}" for ln in chain))
    if stack:
        parts.append("*堆栈*\n" + "\n".join(stack))

    if not parts:
        # 最后兜底：从 hint 或 block 取第一条可读行
        for _, c, _ in reversed(block):
            if not _is_noise_line(c) and not _is_stack_line(c):
                parts.append(f"*根因*\n{c[:500]}")
                break

    out = "\n\n".join(parts)
    if len(out) > max_chars:
        out = out[: max_chars - 1] + "…"
    return redact_secrets_for_display(out)


def build_slack_digest_blocks(
    *,
    source: str,
    task_name: str,
    namespace: str,
    pod_name: str,
    alert_type: str,
    keyword: str,
    digest: str,
    log_url: str | None = None,
) -> list[dict]:
    header_pod = pod_name or source
    blocks: list[dict] = [{
        "type": "header",
        "text": {"type": "plain_text", "text": f"🚨 {namespace}/{header_pod}", "emoji": True},
    }]
    meta = f"*任务* `{task_name}`  ·  *告警* `{alert_type}`  ·  *关键字* `{keyword}`"
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": meta}})

    if digest:
        digest = redact_secrets_for_display(digest)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": digest},
        })

    if log_url:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"<{log_url}|查看完整日志>"}],
        })
    return blocks[:50]
