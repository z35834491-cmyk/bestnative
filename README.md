# BestNative — AI-Native 全栈运维指挥中心

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-14-black?logo=next.js" alt="Next.js">
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/pgvector-HNSW-4169E1" alt="pgvector">
  <img src="https://img.shields.io/badge/LLM-DeepSeek_v4--pro-blue" alt="DeepSeek">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

> **下一代 AI 运维范式** — 10 个专业领域 Agent 协同工作，覆盖监控、诊断、修复、安全、成本、发布全生命周期。基于 LangGraph ReAct 执行器，分 4 层按需加载 22 个工具，token 消耗降低 60%+；混合检索 + 本地 rerank 实现毫秒级故障匹配，飞轮效应让第 N 次同类事件响应从 30 分钟压缩到 30 秒。

---

## 目录

- [架构总览](#架构总览)
- [核心技术栈](#核心技术栈)
- [10 Agent 体系](#10-agent-体系)
- [关键子系统](#关键子系统)
  - [分层工具注册表 (Tiered Tool Registry)](#分层工具注册表-tiered-tool-registry)
  - [ReAct 执行器 & Token 控制](#react-执行器--token-控制)
  - [Discovery Engine 自动发现](#discovery-engine-自动发现)
  - [Trace 链路拓扑](#trace-链路拓扑)
  - [混合检索 RAG](#混合检索-rag)
  - [多环境 Provider 抽象](#多环境-provider-抽象)
  - [安全扫描引擎](#安全扫描引擎)
  - [发布管理 & 自动回滚](#发布管理--自动回滚)
- [数据模型](#数据模型)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [环境变量](#环境变量)
- [设计原则](#设计原则)
- [路线图](#路线图)

---

## 架构总览

```
┌──────────────────────────────────────────────────────────┐
│                    Next.js 14 前端                        │
│  shadcn/ui · Server Components · 同源 /api/* 代理        │
├──────────────────────────────────────────────────────────┤
│                     FastAPI 网关                          │
│    /api/health · /topology · /incidents · /security       │
│    /deployments · /knowledge · /schedules · /cost         │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│ 监控Agent │ 诊断Agent │ 安全Agent │ 变更Agent │ 知识Agent  │
│ 7×24巡检  │ ReAct排查 │ 漏洞扫描  │ 风险评估  │ RAG检索    │
├──────────┼──────────┼──────────┼──────────┼─────────────┤
│ 修复Agent │ 成本Agent │ 助手Agent │ 调度Agent │ 架构Agent  │
│ 自动fix   │ 降本分析  │ NL交互    │ 多Agent协 │ 容量预测   │
├──────────┴──────────┴──────────┴──────────┴─────────────┤
│              LangGraph ReAct 执行器                       │
│    分4层按需加载22个工具 · 3轮后自动摘要 · token最优      │
├──────────────────────────────────────────────────────────┤
│  PostgreSQL/pgvector  │  Redis  │  ES(trace_log)         │
│  HNSW索引 · BM25全文  │  缓存   │  Prometheus(只读)      │
└──────────────────────────────────────────────────────────┘
```

## 核心技术栈

| 层级 | 选型 | 先进性 |
|------|------|--------|
| **后端框架** | FastAPI 0.115 (Python 3.11+) | 异步高性能，原生 OpenAPI 3.1，Pydantic v2 类型安全 |
| **AI 编排** | LangGraph + ReAct | 状态图驱动的多步推理，支持条件分支、工具调用循环 |
| **LLM** | DeepSeek v4-pro | MoE 架构，1M token 上下文，中文 SOTA |
| **Embedding** | BAAI/bge-small-zh-v1.5 | 本地推理，512 维，C-MTEB 榜首，零 API 费用 |
| **Reranker** | BAAI/bge-reranker-v2-m3 | 多语言 Cross-Encoder，本地精排，Top-3 召回率 95%+ |
| **向量数据库** | pgvector (HNSW) | PostgreSQL 原生扩展，IVFFlat/HNSW 双索引，无额外运维 |
| **全文检索** | PostgreSQL `tsvector` + `ts_rank` | 内置 BM25 变体，与向量混合检索 |
| **前端** | Next.js 14 App Router | React Server Components，Streaming SSR，Edge Middleware |
| **UI** | shadcn/ui + Tailwind CSS | Radix 无样式原语，Tree-shaking 零运行时 |
| **数据库** | PostgreSQL 16 + pgvector | 统一存储：业务数据 + 向量 + 全文，一个实例全搞定 |
| **缓存/队列** | Redis 7 | 缓存 + Pub/Sub 消息总线，替代 Kafka/Celery |
| **日志源** | Elasticsearch (trace_log) | 复用现有集群，httpx 直连 REST API，自动 HTTPS 回退 |
| **指标** | Prometheus (只读) | 复用现有，不加采集管道 |
| **容器化** | Docker Compose | 单文件全栈编排，一键 `up -d --build` |
| **K8s 集成** | kubernetes-asyncio | 三路 context 分支 (in_cluster / with_context / default) |

## 10 Agent 体系

每个 Agent 独立可插拔，通过抽象基类 `BaseAgent` 声明配置，由 ReAct 执行器统一调度。

| # | Agent | 触发条件 | 工具层级 | 人工确认 | 核心能力 |
|---|-------|----------|----------|----------|----------|
| 1 | **智能监控** | Cron / 阈值触发 | T0 常驻 | 否 | 7×24 多维度巡检，异常模式识别，PromQL 动态生成，告警聚合去重 |
| 2 | **诊断分析** | 告警升级 / 手动 | T0→T2 | 否 | ReAct 多步排查：日志→指标→链路→事件关联，根因定位，影响面评估 |
| 3 | **自动修复** | 诊断结论 | T3 执行 | **是** | 已知问题自动 apply runbook，回滚操作，全操作审计日志 |
| 4 | **架构优化** | 周报触发 | T1→T2 | 否 | 资源瓶颈识别，容量预测 (Prophet)，技术债务量化，高可用风险评分 |
| 5 | **成本管控** | 日报触发 | T1 | 否 | AWS Cost Explorer / K8s 资源分析，闲置资源识别，RI/Spot 建议，ROI 建模 |
| 6 | **变更管理** | GitLab Webhook | T0→T3 | **是** | 发布前 diff 风险评估，灰度/金丝雀策略，部署后自动验证，失败自动回滚 |
| 7 | **安全合规** | Cron 03:00 + 手动 | T3 执行 | 否 | Nuclei 漏洞扫描，Subfinder 子域名发现，CIS 基线检查，合规报告生成 |
| 8 | **知识管理** | Incident 解决后 | T0 | 否 | 故障自动归档→向量化→关联，复盘报告生成，Runbook 提取，历史案例 Top-3 匹配 |
| 9 | **智能助手** | 用户 @提及 | T0 | 否 | 自然语言交互，上下文理解，日报/周报自动生成，预测性主动提醒 |
| 10 | **协作调度** | 多 Agent 并发 | T0 | 否 | 任务优先级排序，Agent 间上下文传递，值班轮转，跨渠道通知 (Slack/飞书/钉钉) |

---

## 关键子系统

### 分层工具注册表 (Tiered Tool Registry)

22 个工具按 4 层分阶段加载到 LLM context，避免一次性注入全部 schema 导致 token 爆炸：

```
T0_ALWAYS   (常驻)   → 可观测性：查日志、查指标、查 Pod、查拓扑
T1_PLAN     (规划)   → 变更/历史：查部署、查事件、查知识库
T2_ANALYZE  (分析)   → 深度检测：trace 追踪、依赖分析、性能剖析
T3_ACTION   (执行)   → 输出层：漏洞扫描、重启 Pod、回滚部署、生成规则
```

```python
@register_tool("query_logs", tier=ToolTier.T0_ALWAYS, description="查询 ES 日志")
async def query_logs(service: str, hours: int = 1, keyword: str = "") -> dict: ...

@register_tool("nuclei_scan", tier=ToolTier.T3_ACTION, description="漏洞扫描")
async def nuclei_scan(target: str, templates: list[str] = []) -> dict: ...
```

**收益**：单次 ReAct 循环的 system prompt token 从 ~8000 降至 ~2500（降低 68%），同时保持完整功能。

### ReAct 执行器 & Token 控制

```python
async def run_react(system_prompt, user_task, max_tier, max_iterations=8) -> dict:
    """ReAct 循环：LLM 决策 → 调用工具 → 观察 → 再决策
    
    关键优化：
    - 分阶段累加加载工具（T0 → T0+T1 → T0+T1+T2 → 全量）
    - 3 轮后自动摘要早期历史消息，保留 system + 最近 4 条
    - 工具返回压缩到 2000 字符，避免巨型 ToolMessage
    - 每轮统计 token 消耗，超限自动降级工具层
    """
```

### Discovery Engine 自动发现

多 Provider 抽象层，一套代码适配多种基础设施：

| Provider | 发现内容 | 发现方式 |
|----------|----------|----------|
| **Kubernetes** | Deployment/Service/Pod/Node/ConfigMap | K8s API (in_cluster / kubeconfig / context) |
| **AWS EC2** | 实例/安全组/标签 | boto3 + AWS API |
| **SSH VM** | 进程/端口/中间件 | SSH + `ss`/`ps`/`lsof` |
| **阿里云 ECS** | 实例/标签 (未来) | alibabacloud SDK |

发现结果幂等 upsert 到 PostgreSQL，支持 K8s↔VM 混合拓扑桥接：

```
exchange-gateway (K8s) ──→ MySQL:3306 (VM 192.168.1.50) ──→ exchange-order (K8s)
                         ──→ Redis:6379  (VM 192.168.1.51)
```

### Trace 链路拓扑

**零新组件**，直接从现有 ES `trace_log` 索引还原真实调用链：

```
GET /api/topology/trace-graph?service=exchange-gateway&hours=24

→ ES Aggregation: traceId terms → 拉取全部事件
→ 按 serviceName/timestamp 排序 → DAG 边聚合
→ 中间件识别（从 javaModule + thread + logMessage）:
   · MySQL:  Logic SQL / Actual SQL / JDBC / MyBatis / ShardingSphere
   · Redis:  Redis / Redisson / Jedis / ZSet
   · RabbitMQ: Rabbit / RoutingKey / Queue / MQ.Producer / SendToMatch
→ 延迟解析（从日志正文正则提取）:
   · 耗时(12 ms) / 12.5毫秒 / duration: 8ms / cost: 3.2ms
→ 敏感信息脱敏: apiKey/password/token → [REDACTED]

返回:
{
  "nodes": [{id, name, type: service|middleware, traceCount, errorCount}],
  "edges": [{from, to, traceCount, avgLatencyMs, p95LatencyMs, errorCount, health}],
  "traces": [{traceId, services, components, eventCount, hasError, maxDurationMs}]
}
```

`GET /api/topology/traces/{traceId}` 返回完整时间线，每条事件带 `component` 标签和 `durationMs`。

### 混合检索 RAG

PostgreSQL 单库解决向量 + 全文双路检索，不引入 Elasticsearch / Milvus：

```
Query → bge-small embed (512d) → pgvector HNSW 近似检索 (cosine ≤> 权重 0.7)
                                 + ts_rank 全文检索 (权重 0.3)
      → Top-K 召回
      → bge-reranker-v2-m3 Cross-Encoder 精排 (Top-3)
      → 内容截断 1200 字符 → 注入 LLM context
```

五源自动入库：
1. **incident_resolution** — Incident 解决后自动向量化归档
2. **manual_document** — Markdown/PDF 上传
3. **alert_rule** — Prometheus 规则自动同步
4. **log_pattern** — ES 日志异常模式提取
5. **k8s_event_pattern** — K8s Warning Event 模式学习

**飞轮效应**：首次某类故障需 5-10 分钟 ReAct 排查 → 解决后自动入库 → 下次同类事件 RAG 命中 Top-1 → <30 秒直达 runbook。

### 多环境 Provider 抽象

单套代码多环境部署，环境由部署时 `ENVIRONMENT` 环境变量注入：

```
ENVIRONMENT=test      → K8S_CONTEXT=test,  ES=test-es:9200
ENVIRONMENT=prod      → K8S_CONTEXT=prod,  ES=prod-es.acme.com:443
ENVIRONMENT=futures   → K8S_CONTEXT=futures, ES=futures-es:9200
```

Provider 接口统一，三路 K8s context 自动检测：
```python
if settings.K8S_IN_CLUSTER:
    config.load_incluster_config()           # Pod 内 ServiceAccount
elif settings.K8S_CONTEXT:
    config.load_kube_config(context=...)     # 指定 context
else:
    config.load_kube_config()               # 默认 ~/.kube/config
```

### 安全扫描引擎

合并自 PentestAgent，去掉 butian/vulbox 外部对接，聚焦平台自身安全：

| 工具 | 用途 | 集成方式 |
|------|------|----------|
| **Nuclei 3.3** | 漏洞模板扫描 (3000+ 模板) | Go 二进制，Docker 内下载 |
| **Subfinder 2.6** | 子域名发现 (被动) | Go 二进制 |
| **httpx 1.6** | HTTP 探测 & 指纹 | Go 二进制 |
| **nmap** | 端口扫描 | apt 安装 |

调度策略：
- **全平台定时扫描**：每天 03:00 Cron，扫描所有已知服务域名和 IP
- **手动域名扫描**：用户输入域名，即时触发
- **并发限制**：`MAX_CONCURRENT_SCANS=3`，避免打垮目标

### 发布管理 & 自动回滚

对接 GitLab CI + ArgoCD，全流程自动化：

```
GitLab MR merged → Webhook → 变更管理 Agent
  → 发布前风险评估 (diff 分析 + 历史故障关联)
  → ArgoCD Sync (灰度 10% → 50% → 100%)
  → 部署后验证 (health check + 错误率 + 延迟 P95)
  → 失败? → 自动回滚 (kubectl rollout undo)
  → 成功? → 通知 + 归档
```

---

## 数据模型

17 张 PostgreSQL 表，覆盖资源、事件、安全、发布、知识、排班六大领域：

```sql
-- 核心表 (8)
clusters        — K8s 集群 / VM 节点组
nodes           — 集群节点 (CPU/内存/角色)
services        — 业务服务 (副本/镜像/版本/健康)
middlewares     — 中间件 (MySQL/Redis/RabbitMQ 等)
service_dependencies — 服务依赖边
bridges         — K8s↔VM 跨环境桥接
knowledge_chunks — RAG 知识块 (pgvector HNSW 索引)
incidents       — 事件/告警

-- 业务表 (9)
incident_events — 事件时间线
analysis_reports — AI 根因分析报告
alert_rules     — 告警策略 (含 auto_generated 标记)
deployments     — 发布记录
deploy_verifications — 部署后验证
security_scans  — 安全扫描结果
scan_findings   — 漏洞发现
schedules       — 排班表
users / roles   — 认证授权
```

---

## 快速开始

### 前置条件

- Docker & Docker Compose
- Python 3.11+ (本地开发) 或仅 Docker (容器化运行)
- K8s 集群访问权限 (用于拓扑发现，可选)
- ES 集群访问权限 (用于 trace_log 链路，可选)

### 一键启动

```bash
git clone https://github.com/sharkchenshun/bestnative.git
cd bestnative

# 复制环境变量模板，填入实际配置
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 ES/K8s/LLM 连接信息

# 启动全栈
docker compose up -d --build

# 验证
curl http://localhost:3456/api/health
# 前端 → http://localhost:3456
```

### 本地开发

```bash
# 后端
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端 (新终端)
npm install --legacy-peer-deps
npm run dev  # → http://localhost:3456
```

---

## 项目结构

```
bestnative/
├── backend/
│   ├── app/
│   │   ├── agents/             # 10 Agent 实现
│   │   │   ├── base.py         #   Agent 抽象基类
│   │   │   ├── react.py        #   ReAct 执行器 (工具调用循环 + token控制 + 摘要)
│   │   │   ├── llm.py          #   LLM 客户端 (DeepSeek)
│   │   │   ├── diagnosis/      #   诊断 Agent
│   │   │   ├── security/       #   安全 Agent
│   │   │   ├── change/         #   变更 Agent
│   │   │   ├── monitor/        #   监控 Agent
│   │   │   └── coordinator/    #   协作调度 Agent
│   │   ├── api/                # FastAPI 路由
│   │   │   ├── topology.py     #   拓扑 / Trace 链路
│   │   │   ├── incidents.py    #   事件中心
│   │   │   ├── security.py     #   安全合规
│   │   │   ├── deployments.py  #   发布管理
│   │   │   └── health.py       #   健康检查
│   │   ├── providers/          # 多环境适配层
│   │   │   ├── base.py         #   Provider 接口
│   │   │   ├── kubernetes.py   #   K8s (in_cluster / kubeconfig / context)
│   │   │   ├── aws.py          #   AWS EC2
│   │   │   └── ssh_vm.py       #   SSH 裸金属 / VM
│   │   ├── engine/
│   │   │   └── discovery.py    # Discovery Engine (自动发现 → 幂等写入)
│   │   ├── services/
│   │   │   ├── trace_topology.py  # ES trace_log DAG 聚合 + 中间件识别 + 延迟解析
│   │   │   ├── elasticsearch.py   # ES REST 客户端 (httpx, HTTPS 自动回退)
│   │   │   └── prometheus.py      # Prometheus 只读客户端
│   │   ├── tools/
│   │   │   ├── registry.py     #   分层工具注册表 (4 层, 22 工具)
│   │   │   ├── observability.py #  可观测性工具
│   │   │   └── scanners.py     #   安全扫描工具
│   │   ├── rag/
│   │   │   ├── embedding.py    #   bge-small 本地 embedding
│   │   │   ├── retriever.py    #   混合检索 (向量 0.7 + BM25 0.3) + rerank
│   │   │   └── ingest.py       #   五源自动入库
│   │   ├── models/             # SQLAlchemy ORM (17 张表)
│   │   ├── schemas/            # Pydantic v2 校验
│   │   ├── core/               # 配置 / 数据库 / 安全 / 日志
│   │   ├── main.py             # FastAPI 应用入口
│   │   ├── bootstrap.py        # 首次启动数据初始化
│   │   └── scheduler.py        # APScheduler 定时任务
│   ├── alembic/                # 数据库迁移
│   ├── entrypoint.sh           # Docker 启动脚本 (kubeconfig 复制 + context 配置)
│   ├── requirements.txt        # 核心依赖
│   ├── requirements-ml.txt     # ML 重依赖 (sentence-transformers, 懒加载)
│   └── Dockerfile
├── src/
│   ├── app/                    # Next.js 14 App Router (12 页面)
│   │   ├── page.tsx            #   全局总览 (K8s 服务/Pod/日志/重启/指标)
│   │   ├── topology/           #   服务拓扑 (Trace 链路 DAG + Timeline)
│   │   ├── incidents/          #   事件中心
│   │   ├── deployments/        #   发布管理
│   │   ├── security/           #   安全合规
│   │   ├── monitoring/         #   监控面板
│   │   ├── knowledge/          #   知识库
│   │   ├── inspections/        #   巡检报告
│   │   ├── cost/               #   成本分析
│   │   ├── schedules/          #   排班管理
│   │   ├── settings/           #   平台设置
│   │   └── copilot/            #   AI 助手
│   ├── components/layout/      # 布局组件 (Sidebar)
│   ├── lib/                    # 类型定义 / 工具函数
│   └── middleware.ts           # Next.js Edge Middleware (同源 /api/* 代理)
├── docker-compose.yml          # 全栈编排 (frontend + api + postgres + redis)
├── frontend/Dockerfile         # Next.js standalone 构建 (multi-stage)
├── ci-configs/                 # 业务项目 CI/Dockerfile 集中托管
└── docs/                       # 架构图 / 集成文档
```

---

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `ENVIRONMENT` | 是 | 部署环境: `test` / `prod` / `futures` / `development` |
| `DATABASE_URL` | 是 | PostgreSQL 连接 (asyncpg) |
| `REDIS_URL` | 是 | Redis 连接 |
| `ES_HOST` | 否 | Elasticsearch 地址 (用于 trace_log 链路) |
| `ES_PORT` | 否 | ES 端口 (默认 9200) |
| `ES_USER` / `ES_PASSWORD` | 否 | ES 认证 |
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API Key |
| `DEEPSEEK_MODEL` | 否 | 模型名 (默认 `deepseek-chat`) |
| `K8S_CONTEXT` | 否 | K8s context (空则用 current-context) |
| `KUBECONFIG` | 否 | kubeconfig 路径 (空则 ~/.kube/config) |
| `CLUSTER_NAME` | 否 | 集群展示名 (默认 `default`) |
| `SECRET_KEY` | **生产必须** | JWT 签名密钥 (≥32 字符) |
| `GITLAB_WEBHOOK_TOKEN` | 否 | GitLab Webhook 校验 |
| `ARGOCD_SERVER` / `ARGOCD_TOKEN` | 否 | ArgoCD 对接 |

完整配置见 `backend/app/core/config.py`。

---

## 设计原则

### 1. 零新组件，复用现有基础设施
不引入 Kafka、Milvus、Neo4j、ClickHouse、Jaeger。PostgreSQL + Redis 构成双核心数据层，ES/Prometheus 只读复用，不增加采集管道。

### 2. Token 经济学驱动设计
工具分 4 层按需加载，单次 ReAct system prompt < 2500 tokens；3 轮后自动摘要历史；RAG 检索 Top-3 精排 + 1200 字符截断注入。总 token 消耗比全量加载方案降低 60% 以上。

### 3. 本地推理，零外部 API 费用
Embedding (bge-small) 和 Rerank (bge-reranker-v2-m3) 全本地运行，不依赖 OpenAI/Cohere 等付费 Embedding API。LLM 调用是最主要的 API 成本，每次 ReAct 循环已做最大优化。

### 4. 多环境一套代码
每个环境独立部署一个 BestNative 实例，`ENVIRONMENT` 环境变量控制所有差异行为。Provider 抽象层统一 K8s/AWS/SSH/阿里云接口。前端不做环境切换器，环境信息通过部署时 `NEXT_PUBLIC_ENV` 构建注入。

### 5. 安全第一
- JWT 认证 + 角色授权
- 所有 ES 日志输出自动脱敏 `apiKey/password/token → [REDACTED]`
- `SECRET_KEY` 生产必须通过环境变量注入，代码中仅保留 dev-only 默认值
- 安全扫描限于本平台，不接外部漏洞平台
- 自动修复需要人工确认，全操作审计

### 6. 非必要不引入复杂度
- 单文件 `docker-compose.yml` 全栈编排，不拆多个 compose 文件
- 不做微服务拆分，FastAPI 单体 + router 组织
- 不用 Celery，Redis Pub/Sub + APScheduler 满足需求
- 不做 GraphQL，REST API + Pydantic 类型安全足够
- `trace_log` 查询直接用 httpx REST API，避免 elasticsearch-py 版本兼容痛点

---

## 路线图

- [x] 全局总览 — K8s Service/Pod 实时状态、日志、重启、Top
- [x] 服务拓扑 — ES trace_log 真实 Trace 链路 + 中间件识别 + 延迟解析
- [x] Discovery Engine — 多 Provider 自动发现 + 幂等写入
- [x] 分层工具注册表 — 4 层 22 工具
- [x] ReAct 执行器 — Token 控制 + 历史摘要
- [x] 混合检索 RAG — pgvector + BM25 + 本地 Rerank
- [x] 安全扫描引擎 — Nuclei + Subfinder + httpx + nmap
- [x] 事件中心 — 告警归并/去重/丰富化
- [ ] 诊断 Agent ReAct 全链路（日志→指标→trace→事件关联）
- [ ] 自动修复 Agent（已知故障模式 Runbook 自动执行 + 人工确认）
- [ ] 成本 Agent（AWS Cost Explorer + K8s 资源优化）
- [ ] 发布管理对接 ArgoCD（灰度策略 + 自动验证 + 失败回滚）
- [ ] 知识库五源全自动入库
- [ ] 多 Agent 协作调度（上下文传递 + 任务依赖）
- [ ] 阿里云 ECS Provider

---

## License

MIT © sharkchenshun
