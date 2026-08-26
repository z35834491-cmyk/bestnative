# ci-configs/ — 集中托管 CI/Dockerfile

Shore 统一管理的 CI/CD 配置。业务项目通过 GitLab CI `include` 引用此仓库中的配置，
不再各自维护 `.gitlab-ci.yml` 和 `Dockerfile`。

## 目录

```
ci-configs/
  templates/
    ci-common.yml          # 共享 anchors（日志/Slack/全局变量模板）
    Dockerfile.java         # Java 项目通用 Dockerfile 模板
    Dockerfile.node         # Node 项目通用 Dockerfile 模板
  <project-name>/
    ci.yml                  # GitLab CI Pipeline（引用 templates/ci-common.yml）
    Dockerfile              # 项目专属 Dockerfile
```

## 工作原理

```
业务项目 .gitlab-ci.yml:
  include:
    - project: 'sre/bestnative'
      ref: main
      file: 'ci-configs/<project-name>/ci.yml'

  → GitLab 在项目 repo 的 context 下加载 Shore 的 CI 配置
  → 运行环境仍是项目 repo（代码、Runner 不变）
  → 仅 CI 逻辑集中管理
```

## 添加新项目

1. 复制 `templates/` 模板到 `ci-configs/<project-name>/`
2. 修改 `ci.yml` 中的项目专属变量：
   - `jar_artifacts_paths` / `node_artifacts_paths`（产物路径）
   - `API_POM_PATH` / `BIZ_POM_PATH`（Java 多模块）
   - `BASE_IMAGE`（基础镜像）
   - `ARGOCD_APP_NAME`（ArgoCD 应用名）
3. 在业务项目 `.gitlab-ci.yml` 中添加 `include`
4. 删除业务项目中的旧 `.gitlab-ci.yml` 和 `Dockerfile`
