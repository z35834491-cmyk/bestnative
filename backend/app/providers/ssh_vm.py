# ============================================================
# app/providers/ssh_vm.py — VM 中间件发现（SSH + 端口探测）
# 用于测试环境：中间件跑在 VM 上，通过 SSH 探测进程/端口
# 安全：只读命令，禁用交互 shell，密钥优先于密码
# ============================================================

import asyncio

from app.core.logging import get_logger
from app.providers.base import (
    DiscoveredMiddleware,
    DiscoveryResult,
    InfrastructureProvider,
)

logger = get_logger("provider.ssh")

PORT_TO_MIDDLEWARE = {
    3306: "mysql", 5432: "postgresql", 6379: "redis",
    5672: "rabbitmq", 27017: "mongodb", 9200: "elasticsearch",
}


class SSHVMProvider(InfrastructureProvider):
    """通过 SSH 连接 VM，探测监听端口识别中间件。

    config: { host, port(22), user, key_path | password, probe_ports: [..] }
    """
    provider_type = "ssh_vm"

    async def discover(self) -> DiscoveryResult:
        result = DiscoveryResult(cluster_name=self.name, provider=self.provider_type)
        listening = await self._get_listening_ports()

        for port in listening:
            mw_type = PORT_TO_MIDDLEWARE.get(port)
            if mw_type:
                result.middlewares.append(DiscoveredMiddleware(
                    name=f"{self.name}-{mw_type}", type=mw_type,
                    host=self.config.get("host", ""), port=port,
                    discovered_from="ssh_probe",
                ))
        logger.info("ssh.discover.done", host=self.config.get("host"),
                    middlewares=len(result.middlewares))
        return result

    async def _get_listening_ports(self) -> set[int]:
        """SSH 执行 `ss -tlnp` 获取监听端口（只读）。"""
        cmd = "ss -tln 2>/dev/null || netstat -tln 2>/dev/null"
        out = await self._ssh_exec(cmd)
        ports: set[int] = set()
        for line in out.splitlines():
            # 匹配 :PORT 格式
            for token in line.split():
                if ":" in token:
                    tail = token.rsplit(":", 1)[-1]
                    if tail.isdigit():
                        ports.add(int(tail))
        return ports

    async def _ssh_exec(self, command: str) -> str:
        """在 executor 中跑 paramiko（同步库），避免阻塞事件循环。"""
        def _run() -> str:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())  # 安全：拒绝未知主机
            try:
                client.load_system_host_keys()
                kwargs = {
                    "hostname": self.config["host"],
                    "port": self.config.get("port", 22),
                    "username": self.config["user"],
                    "timeout": 10,
                }
                if self.config.get("key_path"):
                    kwargs["key_filename"] = self.config["key_path"]
                elif self.config.get("password"):
                    kwargs["password"] = self.config["password"]
                client.connect(**kwargs)
                _, stdout, _ = client.exec_command(command, timeout=15)
                return stdout.read().decode("utf-8", errors="replace")
            finally:
                client.close()

        return await asyncio.get_event_loop().run_in_executor(None, _run)

    async def health_check(self) -> dict:
        try:
            await self._ssh_exec("echo ok")
            return {"status": "ok", "provider": self.provider_type, "host": self.config.get("host")}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "error": str(e)}
