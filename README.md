# BestNative — AI-Native 全栈运维指挥中心

基于 AI Agent 体系的新一代运维平台，覆盖监控、诊断、修复、安全、成本、发布全生命周期。

## 技术栈

| 层 | 选型 |
|------|------|
| 后端 | FastAPI (Python 3.11+) |
| 前端 | Next.js 14 + shadcn/ui |
| 数据库 | PostgreSQL + pgvector |
| 缓存 | Redis |
| 日志检索 | Elasticsearch（复用现有） |
| LLM | DeepSeek v4-pro |
| Embedding | bge-small-zh-v1.5（本地） |
| 容器化 | Docker Compose |

## 10 大 AI Agent

1. **智能监控 Agent** — 7×24 巡检，异常模式识别，告警聚合
2. **诊断分析 Agent** — ReAct 根因分析，日志/指标/链路关联排查
3. **自动修复 Agent** — 常见问题自动修复 + 人工确认 + 全操作审计
4. **架构优化 Agent** — 瓶颈分析，容量预测，高可用风险评估
5. **成本管控 Agent** — 实时成本分析，闲置资源识别，降本建议
6. **变更管理 Agent** — 发布前风险评估，自动发布，发布后验证
7. **安全合规 Agent** — 漏洞扫描，配置合规检查，合规报告
8. **知识管理 Agent** — 故障自动归档，复盘报告，历史案例匹配
9. **智能助手 Agent** — 自然语言交互，日报/周报，预测性提醒
10. **协作调度 Agent** — 多 Agent 协同，任务优先级，值班调度

## 核心功能

- **全局总览** — K8s 集群服务/Pod 实时状态、日志、重启、资源 Top
- **服务拓扑** — 基于 ES `trace_log` 的 Trace 链路拓扑，自动识别 MySQL/Redis/RabbitMQ 中间件节点，展示调用延迟
- **事件中心** — 告警归并/去重/丰富化/路由 + AI 分析
- **发布管理** — 变更风险评估，自动发布，回滚
- **安全合规** — 定时全平台漏洞扫描 + 手动域名扫描
- **知识库** — RAG 混合检索（向量 + BM25），五源自动入库
- **成本分析** — 多环境资源成本，闲置识别，优化建议

## 本地开发

```bash
# 启动全栈
docker compose up -d --build

# 前端 http://localhost:3456
# 后端 API http://localhost:3456/api/*
```

### 环境变量

复制 `.env.example` 为 `.env`，配置 ES/K8s/LLM 连接信息。

```env
# Elasticsearch（复用现有集群）
ES_HOST=your-es-host
ES_PORT=9200
ES_USER=your-user
ES_PASSWORD=your-password

# K8s
K8S_CONTEXT=test

# LLM
DEEPSEEK_API_KEY=your-key
DEEPSEEK_MODEL=deepseek-v4-pro
```

## 项目结构

```
bestnative/
├── backend/
│   └── app/
│       ├── api/           # REST API 路由
│       ├── agents/        # 10 个 AI Agent 实现
│       ├── providers/     # K8s / AWS / SSH 多环境适配
│       ├── services/      # ES / Prometheus / Trace 查询
│       ├── models/        # SQLAlchemy 数据模型
│       ├── schemas/       # Pydantic 校验
│       └── core/          # 配置 / 日志
├── src/
│   ├── app/               # Next.js 页面（12 个路由）
│   └── lib/               # 类型 / 工具 / API 客户端
└── docker-compose.yml     # 全栈编排
```

## 设计原则

- **轻量化** — PostgreSQL + Redis 双核心，复用现有 ES/Prometheus，不引入 Kafka/Milvus/Neo4j
- **多环境** — Provider 抽象层，一套代码适配测试 VM / 生产 AWS / 期货 K8s
- **Token 优化** — 工具分 4 层按阶段加载，RAG 检索 Top-3 精排 + 压缩
- **经验积累** — Incident Resolution 自动入向量库，飞轮效应（首次 5-10min → 第三次 <30s）

## License

MIT
