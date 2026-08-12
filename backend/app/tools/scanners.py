# ============================================================
# app/tools/scanners.py — 安全扫描工具（合并自 PentestAgent）
# nmap / nuclei / subfinder / httpx —— 非 shell=True，防命令注入
# ============================================================

import asyncio
import json
import shutil
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod

from app.core.logging import get_logger

logger = get_logger("tools.scanner")


class ScanTool(ABC):
    name: str = "base"

    @abstractmethod
    def build_command(self, target: str, options: dict | None = None) -> list[str]:
        ...

    @abstractmethod
    def parse_output(self, lines: list[str]) -> list[dict]:
        ...

    def available(self) -> bool:
        return shutil.which(self.name) is not None

    async def run(self, target: str, options: dict | None = None, timeout: int = 1800) -> list[dict]:
        """执行扫描，收集全部输出后解析。非 shell，参数列表防注入。"""
        if not self.available():
            logger.warning("scanner.missing", tool=self.name)
            return []
        cmd = self.build_command(target, options)
        logger.info("scanner.run", tool=self.name, cmd=" ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        lines: list[str] = []
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            lines = stdout.decode("utf-8", errors="replace").splitlines()
        except asyncio.TimeoutError:
            proc.kill()
            logger.warning("scanner.timeout", tool=self.name, target=target)
        return self.parse_output(lines)


class NmapTool(ScanTool):
    name = "nmap"

    def build_command(self, target: str, options: dict | None = None) -> list[str]:
        ports = (options or {}).get("ports", "1-1000")
        return ["nmap", "-sV", "-sC", "-T4", "-p", ports, "-oX", "-", target]

    def parse_output(self, lines: list[str]) -> list[dict]:
        results = []
        try:
            root = ET.fromstring("\n".join(lines))
            for host in root.findall(".//host"):
                ip_elem = host.find(".//address[@addrtype='ipv4']")
                ip = ip_elem.get("addr", "") if ip_elem is not None else ""
                for port_elem in host.findall(".//port"):
                    pid = port_elem.get("portid", "")
                    svc = port_elem.find("service")
                    if svc is not None:
                        results.append({
                            "type": "port", "value": f"{ip}:{pid}", "port": int(pid),
                            "protocol": port_elem.get("protocol", ""),
                            "service": svc.get("name", ""),
                            "version": (svc.get("product", "") + " " + svc.get("version", "")).strip(),
                        })
        except ET.ParseError:
            pass
        return results


class NucleiTool(ScanTool):
    name = "nuclei"

    def build_command(self, target: str, options: dict | None = None) -> list[str]:
        severity = (options or {}).get("severity", "critical,high,medium")
        return ["nuclei", "-u", target, "-severity", severity, "-jsonl", "-silent"]

    def parse_output(self, lines: list[str]) -> list[dict]:
        results = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("["):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            info = data.get("info", {})
            classification = info.get("classification", {}) or {}
            results.append({
                "title": info.get("name", data.get("template-id", "")),
                "severity": (info.get("severity") or "info").lower(),
                "type": data.get("type", "vulnerability"),
                "target": data.get("host", data.get("matched-at", "")),
                "endpoint": data.get("matched-at", ""),
                "description": info.get("description", ""),
                "cve": (classification.get("cve-id") or [None])[0] if isinstance(classification.get("cve-id"), list) else classification.get("cve-id"),
                "cvss_score": classification.get("cvss-score"),
                "recommendation": info.get("remediation", ""),
                "found_by": "nuclei",
            })
        return results


class SubfinderTool(ScanTool):
    name = "subfinder"

    def build_command(self, target: str, options: dict | None = None) -> list[str]:
        return ["subfinder", "-d", target, "-silent"]

    def parse_output(self, lines: list[str]) -> list[dict]:
        return [{"type": "subdomain", "value": ln.strip()}
                for ln in lines if ln.strip() and "." in ln]


class HttpxTool(ScanTool):
    name = "httpx"

    def build_command(self, target: str, options: dict | None = None) -> list[str]:
        return ["httpx", "-u", target, "-silent", "-json",
                "-status-code", "-title", "-tech-detect"]

    def parse_output(self, lines: list[str]) -> list[dict]:
        results = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            results.append({
                "type": "url", "value": data.get("url", ""),
                "service": ",".join(data.get("tech", []) or []),
                "extra": {"status_code": data.get("status_code"),
                          "title": data.get("title", "")},
            })
        return results


SCANNERS = {
    "nmap": NmapTool(),
    "nuclei": NucleiTool(),
    "subfinder": SubfinderTool(),
    "httpx": HttpxTool(),
}
