# ============================================================
# app/providers/aws.py — AWS EC2 资源发现（可选，生产环境）
# 只读：使用 readonly role，配合 MFA assume role
# ============================================================

import asyncio

from app.core.logging import get_logger
from app.providers.base import (
    DiscoveredNode,
    DiscoveryResult,
    InfrastructureProvider,
)

logger = get_logger("provider.aws")


class AWSProvider(InfrastructureProvider):
    """AWS EC2 实例发现。

    config: { region, role_arn(可选), profile(可选) }
    权限：只读（etz-prd-sre-aws-readonly-role）
    """
    provider_type = "aws_ec2"

    def _client(self, service: str):
        import boto3
        session_kwargs = {}
        if self.config.get("profile"):
            session_kwargs["profile_name"] = self.config["profile"]
        session = boto3.Session(**session_kwargs)
        return session.client(service, region_name=self.config.get("region", "ap-northeast-1"))

    async def discover(self) -> DiscoveryResult:
        result = DiscoveryResult(cluster_name=self.name, provider=self.provider_type)

        def _run():
            ec2 = self._client("ec2")
            nodes = []
            paginator = ec2.get_paginator("describe_instances")
            for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": ["running"]}]):
                for res in page.get("Reservations", []):
                    for inst in res.get("Instances", []):
                        name = next((t["Value"] for t in inst.get("Tags", [])
                                     if t["Key"] == "Name"), inst["InstanceId"])
                        nodes.append(DiscoveredNode(
                            name=name,
                            internal_ip=inst.get("PrivateIpAddress", ""),
                            role="worker",
                            health="healthy",
                        ))
            return nodes

        result.nodes = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("aws.discover.done", region=self.config.get("region"), nodes=len(result.nodes))
        return result

    async def health_check(self) -> dict:
        try:
            def _run():
                return self._client("sts").get_caller_identity()
            ident = await asyncio.get_event_loop().run_in_executor(None, _run)
            return {"status": "ok", "provider": self.provider_type, "account": ident.get("Account")}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "error": str(e)}
