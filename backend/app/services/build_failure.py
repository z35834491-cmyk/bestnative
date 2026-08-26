# ============================================================
# build_failure.py — 构建/启动失败日志采集与分类
# ============================================================

from __future__ import annotations

import re

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("build_failure")

# GitLab Runner / CI 日志中的 ANSI 与裸 CSI（ESC 常被剥离成 [0K、[36;1m）
_ANSI_ESCAPE = re.compile(
    r"\x1b(?:\[[0-9;]*[A-Za-z]|\].*?(?:\x07|\x1b\\))",
)
_GITLAB_CSI = re.compile(
    r"\[(?:\d+(?:;\d+)*)?[A-Za-z]"  # [0K
    r"|\[\d*(?:;\d*)*m",             # [0m [0;m [36;1m
)
# 行首 timestamp + GitLab 重复空白
_TS_LINE = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.+-]+Z?\s*")

_STARTUP_JOB_KEYS = ("deploy", "helm", "argocd", "kubectl", "rollout", "release", "startup", "start")
_BUILD_JOB_KEYS = ("build", "docker", "maven", "gradle", "compile", "package", "image", "test", "lint")

_BRANCH_NS = {
    "dev": "biz-system",
    "test": "biz-system",
    "main": "biz-system",
}


def classify_failure_kind(failed_job: dict | None) -> str:
    """build=CI 构建失败；startup=部署后 Pod 启动失败。"""
    if not failed_job:
        return "build"
    text = f"{failed_job.get('stage', '')} {failed_job.get('name', '')}".lower()
    if any(k in text for k in _STARTUP_JOB_KEYS):
        return "startup"
    if any(k in text for k in _BUILD_JOB_KEYS):
        return "build"
    # deploy 阶段失败但 job 名不明显时，偏向 startup
    if failed_job.get("stage", "").lower() in {"deploy", "production", "release"}:
        return "startup"
    return "build"


def namespace_for_branch(branch: str) -> str:
    return _BRANCH_NS.get((branch or "").lower(), "biz-system")


def fetch_pod_startup_logs(service: str, branch: str, *, tail_lines: int = 200) -> str:
    """拉取服务 Pod 启动/崩溃日志（同步，供 build 通知使用）。"""
    try:
        from kubernetes import client, config as k8s_config
    except ImportError:
        return ""

    namespace = namespace_for_branch(branch)
    ctx = settings.K8S_CONTEXT or None
    try:
        if settings.K8S_IN_CLUSTER:
            k8s_config.load_incluster_config()
        elif settings.KUBECONFIG:
            k8s_config.load_kube_config(config_file=settings.KUBECONFIG, context=ctx)
        else:
            k8s_config.load_kube_config(context=ctx)
    except Exception as exc:  # noqa: BLE001
        logger.debug("build_failure.k8s_config.failed", error=str(exc)[:80])
        return ""

    api = client.CoreV1Api()
    try:
        pods = api.list_namespaced_pod(namespace).items
    except Exception as exc:  # noqa: BLE001
        logger.debug("build_failure.list_pods.failed", ns=namespace, error=str(exc)[:80])
        return ""

    svc = (service or "").lower()
    matched = [p for p in pods if svc and svc in (p.metadata.name or "").lower()]
    if not matched:
        short = svc.replace("-", "")
        matched = [
            p for p in pods
            if short and short in (p.metadata.name or "").lower().replace("-", "")
        ]
    if not matched:
        return ""

    def _score(p) -> int:
        phase = p.status.phase or ""
        restarts = sum(s.restart_count for s in (p.status.container_statuses or []))
        waiting_reason = ""
        for st in p.status.container_statuses or []:
            if st.state and st.state.waiting:
                waiting_reason = st.state.waiting.reason or ""
        bad = phase not in ("Running", "Succeeded") or restarts > 0
        bonus = 10 if bad else 0
        if waiting_reason in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
            bonus += 20
        return bonus + restarts

    pod = max(matched, key=_score)
    pod_name = pod.metadata.name
    container = pod.spec.containers[0].name if pod.spec.containers else ""
    try:
        raw = api.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
            timestamps=False,
        )
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return raw or ""
    except Exception as exc:  # noqa: BLE001
        logger.debug("build_failure.pod_log.failed", pod=pod_name, error=str(exc)[:80])
        return ""


def clean_build_log(text: str) -> str:
    """清洗 CI 构建日志：去掉 ANSI/GitLab Runner 控制码，保留可读文本。"""
    if not text:
        return ""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    s = _ANSI_ESCAPE.sub("", s)
    s = _GITLAB_CSI.sub("", s)
    lines: list[str] = []
    for raw in s.splitlines():
        line = _TS_LINE.sub("", raw).strip()
        line = re.sub(r"\s{2,}", " ", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def tail_ci_log(text: str, max_chars: int = 8000) -> str:
    cleaned = clean_build_log(text)
    if not cleaned:
        return ""
    return cleaned[-max_chars:] if len(cleaned) > max_chars else cleaned
