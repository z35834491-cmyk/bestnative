# CI/CD 迁移清单 — 业务项目 CI → Shore 集中管理

> 目标：业务项目删掉 `.gitlab-ci.yml` 和 `Dockerfile`，仅保留一行 `include` 引用。
> 实际 CI 逻辑全部托管在 `bestnative/ci-configs/` 下，由运维团队统一维护和优化。

---

## 整体流程

```
                         ┌─────────────────────┐
dev push code ──────────→│  GitLab CI (thin)    │
                         │  include: bestnative │
                         └────────┬────────────┘
                                  │ 加载 ci-configs/<project>/ci.yml
                                  ▼
                         ┌─────────────────────┐
                         │ prepare    (env vars)│
                         │ download   (maven xml)│
                         │ package    (mvn/pnpm)│
                         │ build      (docker)  │
                         │ update-helm          │
                         │ deploy     (argocd)  │
                         └────────┬────────────┘
                                  │
                         ┌────────▼────────────┐
                         │ ArgoCD sync + verify │
                         │ Shore webhook   │
                         └──────────────────────┘
```

---

## 第一步：GitLab 权限

| 权限项 | 说明 | 配置位置 |
|:-------|:-----|:---------|
| bestnative 仓库读取权限 | 业务项目的 CI runner 需要能通过 `include: project` 引用本仓库 CI 文件 | GitLab → `sre/bestnative` → Settings → CI/CD → Token Access → 允许 `sre/*` group 访问 |
| `GITLAB_API_TOKEN` | CI 中下载 maven settings 文件和 clone Helm 仓库用的 API Token | GitLab → Settings → Access Tokens → 创建 `api` + `read_repository` scope 的 token → 设为 Group CI Variable |
| `GITLAB_URL` | GitLab 实例地址 | 设为 Group CI Variable |
| `SLACK_URL` | Slack webhook URL | 已有，无需变更 |
| `SLACK_USER_ID_MAP` | GitLab 用户名 → Slack 用户 ID 映射 | 已有，无需变更 |

---

## 第二步：Harbor / ECR 权限

| 权限项 | 说明 | 配置位置 |
|:-------|:-----|:---------|
| `HARBOR_HOST` | Harbor 地址，如 `harbor.example.com` | 已有 Group CI Variable |
| `HARBOR_USERNAME` | Harbor 登录用户名 | 已有 |
| `HARBOR_PASSWORD` | Harbor 登录密码 | 已有 |
| `HARBOR_PROJECT` | Harbor 项目名，如 `exchange` | 已有 |
| `HARBOR_HOST_TAILSCALE` | Tailscale 网络的 Harbor 地址 | 已有 |
| `ECR_PROD_ADDR` | 生产 ECR 地址（main 分支用） | 已有 |

---

## 第三步：ArgoCD 权限

| 权限项 | 说明 | 配置位置 |
|:-------|:-----|:---------|
| `ARGOCD_DEVELOP_URL` | dev 环境 ArgoCD 地址 | 已有 Group CI Variable |
| `ARGOCD_DEVELOP_TOKEN` | dev 环境 ArgoCD Auth Token | 已有 |
| `ARGOCD_TEST_URL` | test 环境 ArgoCD 地址 | 已有 |
| `ARGOCD_TEST_TOKEN` | test 环境 ArgoCD Auth Token | 已有 |

> 生产 main 分支不走 ArgoCD CI 自动部署（现有流程：main 仅 update-helm + push OCI，手动触发部署或通过 Shore webhook）。与现有行为一致。

---

## 第四步：逐个业务项目迁移

### 4.1 复制配置到 Shore

```bash
cd bestnative/ci-configs/

# 为每个项目创建目录（以 exchange-xxl-job 为例）
mkdir -p exchange-xxl-job
cp templates/ci-common.yml ../

# 从现有 cicd 仓库复制 Dockerfile
cp ~/Desktop/cicd/exchange-xxl-job/Dockerfile exchange-xxl-job/
```

### 4.2 修改项目 ci.yml

每个项目的 `ci.yml` 只需定义**项目专属变量**，其余引用 `templates/ci-common.yml`。

**Java 项目模板**（如 exchange-xxl-job）：

```yaml
# ci-configs/exchange-xxl-job/ci.yml
---
include:
  - project: 'sre/bestnative'
    ref: main
    file: 'ci-configs/templates/ci-common.yml'

stages:
  - prepare
  - download
  - package
  - build
  - update
  - deploy

# ==== 项目专属：产物路径 ====
.jar_artifacts_paths: &jar_artifacts_paths
  - xxl-job-admin/target/*.jar

# ==== 项目专属变量（覆盖模板默认值）====
variables:
  BASE_IMAGE: "${HARBOR_HOST}/base/amazoncorretto:11"
  BUILD_IMAGE_ARGS: "DOCKER_BASE_IMAGE=${BASE_IMAGE}"
  BUILD_CONFIG_ARGS: "JAVA_CONFIG_FILE=${CI_COMMIT_BRANCH}"
  API_POM_PATH: "xxl-job-admin/pom.xml"

prepare_env:
  extends: .default-job-template
  stage: prepare
  artifacts:
    reports:
      dotenv: "${GLOBAL_ENV_FILE}"
    expire_in: 1h
  script:
    - *prepare_env_vars

download_file:
  <<: *notify_slack
  extends: .default-job-template
  stage: download
  dependencies: [prepare_env]
  artifacts:
    paths: ["${MAVEN_SETTING_FILE}"]
    expire_in: 1h
  script:
    - |
      curl -sSk --fail ${CURL_RETRY_CONF} -H "PRIVATE-TOKEN: ${GITLAB_API_TOKEN}" "${MAVEN_DOWNLOAD_URL}" -o "${MAVEN_SETTING_FILE}" > "${RES_TMP_FILE}" 2>&1; EXIT_CODE=$?
      check_fail "配置文件下载" "${EXIT_CODE}" "下载路径 ${MAVEN_DOWNLOAD_URL}"

package:
  <<: *notify_slack
  extends: .default-job-template
  stage: package
  dependencies: [download_file, prepare_env]
  cache:
    key: "${CI_PROJECT_NAME}-${CI_COMMIT_BRANCH}"
    paths: ["${MAVEN_CACHE_PATH}"]
  artifacts:
    paths: *jar_artifacts_paths
    expire_in: 1h
  script:
    - |
      mkdir -p "${MAVEN_CACHE_PATH}"
      mvn -s "${MAVEN_SETTING_FILE}" clean install -DskipTests > "${RES_TMP_FILE}" 2>&1; EXIT_CODE=$?
      if [ "${EXIT_CODE}" -ne 0 ]; then
        rm -rf "${MAVEN_CACHE_PATH}"
        mkdir -p "${MAVEN_CACHE_PATH}"
        mvn -s "${MAVEN_SETTING_FILE}" clean install -DskipTests > "${RES_TMP_FILE}" 2>&1; EXIT_CODE=$?
      fi
      JAR_FILE=$(find . -type f -path "*-biz/target/*.jar" | head -n 1)
      check_fail "Maven 代码包构建" "${EXIT_CODE}" "输出文件 ${JAR_FILE}"

build:
  <<: *notify_slack
  extends: .default-job-template
  stage: build
  dependencies: [prepare_env, package]
  script:
    - |
      dockerd --host="${DOCKER_HOST}" --insecure-registry="${HARBOR_HOST}" --insecure-registry="${HARBOR_HOST_TAILSCALE}" > /dev/null 2>&1 &
      timeout 15 sh -c "until docker info; do sleep 1; done"
      echo "${HARBOR_PASSWORD}" | docker login "${HARBOR_HOST}" -u "${HARBOR_USERNAME}" --password-stdin
      docker buildx build --build-arg "${BUILD_IMAGE_ARGS}" --build-arg "${BUILD_CONFIG_ARGS}" --tag "${FULL_IMAGE}" --push . > "${RES_TMP_FILE}" 2>&1; EXIT_CODE=$?
      check_fail "Docker 构建并推送镜像" "${EXIT_CODE}" "镜像名称 ${FULL_IMAGE}"

update-helm:
  <<: *notify_slack
  extends: .default-job-template
  stage: update
  dependencies: [prepare_env, build]
  script:
    - |
      git clone --branch ${CI_COMMIT_BRANCH} --depth 1 "${HELM_GIT_REPO_URL}"
      cd "${HELM_GIT_REPO_NAME}"
      CHART_VERSION=$(yq e ".version" Chart.yaml)
      [ "${CHART_VERSION}" != "${DEPLOY_VERSION}" ] && yq e -i ".version = \"${DEPLOY_VERSION}\"" Chart.yaml
      yq e -i ".appVersion = \"${DEPLOY_VERSION}\"" Chart.yaml
      CHART_NAME=$(yq e ".name" Chart.yaml)
      yq e -i ".image.repository = \"${HELM_IMAGE_URL}\"" values.yaml
      yq e -i ".image.tag = \"${DEPLOY_VERSION}\"" values.yaml
      git config user.name "$GITLAB_USER_NAME"
      git config user.email "${GITLAB_USER_EMAIL:-cicd@gmail.com}"
      git add values.yaml Chart.yaml
      if git status --porcelain | grep .; then
        git commit -m "更新镜像TAG为 ${DEPLOY_VERSION} by CI"
        git push origin ${CI_COMMIT_BRANCH}
      fi
      helm package .
      echo "${HARBOR_PASSWORD}" | helm registry login "${HARBOR_HOST}" --username "${HARBOR_USERNAME}" --password-stdin
      CHART_TGZ="${CHART_NAME}-${DEPLOY_VERSION}.tgz"
      helm push --plain-http "${CHART_TGZ}" "${HELM_HARBOR_REPO_URL}"
      check_fail "Helm 更新推送" "$?" "Chart ${CHART_TGZ}"

deploy:
  <<: *notify_slack
  extends: .default-job-template
  stage: deploy
  dependencies: [prepare_env]
  rules:
    - if: "$CI_COMMIT_BRANCH =~ /^(dev|test)$/"
      when: on_success
    - when: never
  script:
    - |
      argocd app get "${ARGOCD_APP_NAME}" --server "${ARGOCD_OP_URL}" --auth-token "${ARGOCD_OP_TOKEN}" ${ARGOCD_OPT} -o json > "${RES_TMP_FILE}" 2>&1; EXIT_CODE=$?
      check_fail "获取 ArgoCD 应用" "${EXIT_CODE}"
      APP_JSON=$(cat "${RES_TMP_FILE}")
      CURRENT_VERSION=$(echo "${APP_JSON}" | jq -r ".spec.source.targetRevision")
      if [ "${CURRENT_VERSION}" != "${DEPLOY_VERSION}" ]; then
        argocd app set "${ARGOCD_APP_NAME}" --revision "${DEPLOY_VERSION}" --server "${ARGOCD_OP_URL}" --auth-token "${ARGOCD_OP_TOKEN}" ${ARGOCD_OPT}
      fi
      argocd app sync "${ARGOCD_APP_NAME}" --server "${ARGOCD_OP_URL}" --auth-token "${ARGOCD_OP_TOKEN}" ${ARGOCD_OPT} --prune --force
      argocd app wait "${ARGOCD_APP_NAME}" --server "${ARGOCD_OP_URL}" --auth-token "${ARGOCD_OP_TOKEN}" ${ARGOCD_OPT} --health --timeout 180
      check_fail "ArgoCD 部署" "$?" "${ARGOCD_APP_NAME} → ${DEPLOY_VERSION}"
```

### 4.3 业务项目侧改动

**改前**（`.gitlab-ci.yml` 500+ 行 + `Dockerfile` 30+ 行）：

```
exchange-xxl-job/
  .gitlab-ci.yml     ← 437 行，删除
  Dockerfile          ← 24 行，删除
  src/...
```

**改后**（`.gitlab-ci.yml` 仅 4 行）：

```
exchange-xxl-job/
  .gitlab-ci.yml     ← 4 行 include
  src/...
```

业务项目的 `.gitlab-ci.yml`：

```yaml
include:
  - project: 'sre/bestnative'
    ref: main
    file: 'ci-configs/exchange-xxl-job/ci.yml'
```

### 4.4 注意事项

| 注意点 | 说明 |
|:-------|:-----|
| Dockerfile 位置 | CI 的 `build` job 在项目 repo 根目录执行 `docker build`，Dockerfile 引用的 `COPY ./xxl-job-admin/target/*.jar` 等路径必须与项目 repo 结构一致。项目 repo 不需要保留 Dockerfile（已在 Shore 中），但 COPY 的源路径（jar/node_modules）仍是项目 repo 内的产物 |
| Maven settings 文件 | 仍存在业务项目的 GitLab repo 中（`maven-setting-dev.xml` 等），下载逻辑不变 |
| Helm 仓库 | 仍在 `sre/cicd` 仓库中，update-helm 逻辑不变 |
| Slack 通知 | 逻辑不变，模板收拢到 `ci-common.yml` |
| Webhook 通知 | exchange-web 等有 `notify-release` 额外 job 的，需要在项目 `ci.yml` 中保留 |

---

## 第五步：验证

### 5.1 预先检查

```bash
# 确认 Shore ci-configs 目录完整
ls ci-configs/templates/ci-common.yml     # 共享模板
ls ci-configs/<project>/ci.yml            # 项目 CI
ls ci-configs/<project>/Dockerfile        # 项目 Dockerfile
```

### 5.2 逐项目灰度

1. **选一个低风险项目先试**（如 xxl-job，非交易链路）
2. 在业务项目新建分支，替换 `.gitlab-ci.yml` 为 `include`
3. Push 到 dev 分支 → 观察 GitLab CI 是否正常触发
4. 检查 pipeline 各 stage：prepare → download → package → build → update-helm → deploy
5. 确认 ArgoCD 同步成功、Pod 健康
6. test 分支重复验证
7. main 分支重复验证（无 deploy stage，仅 build + update-helm）
8. 通过后 merge，再迁移下一个项目

### 5.3 回滚方案

如果迁移后 CI 异常，业务项目紧急回滚：

```bash
git revert <迁移commit>
# 或恢复旧的 .gitlab-ci.yml + Dockerfile
```

---

## 第六步：后续优化（Phase 2）

迁移完成后可做：

| 优化项 | 收益 |
|:-------|:-----|
| Dockerfile 公共层提取 | 统一 base image、JVM 参数、OTel agent 注入 → 减少重复 |
| 多模块 Maven 并行构建 | 区分 api/biz/db 模块并行编译 → 提速 |
| CI 缓存策略统一 | cache key、Maven/NPM 缓存路径标准化 |
| 非 Maven 项目模板 | Node/pnpm、Go、Python 项目模板 |
| 构建历史分析（规划中） | 根据历史构建耗时，推荐 JVM 参数 / 镜像优化 |

---

## 权限速查表

| 变量 | 级别 | 是否已有 |
|:-----|:-----|:--------|
| `GITLAB_API_TOKEN` | Group CI Var | 需确认 |
| `GITLAB_URL` | Group CI Var | 需确认 |
| `SLACK_URL` | Group CI Var | ✅ 已有 |
| `SLACK_USER_ID_MAP` | Group CI Var | ✅ 已有 |
| `HARBOR_HOST` | Group CI Var | ✅ 已有 |
| `HARBOR_USERNAME` | Group CI Var | ✅ 已有 |
| `HARBOR_PASSWORD` | Group CI Var | ✅ 已有 |
| `HARBOR_PROJECT` | Group CI Var | ✅ 已有 |
| `HARBOR_HOST_TAILSCALE` | Group CI Var | ✅ 已有 |
| `ARGOCD_DEVELOP_URL` | Group CI Var | ✅ 已有 |
| `ARGOCD_DEVELOP_TOKEN` | Group CI Var | ✅ 已有 |
| `ARGOCD_TEST_URL` | Group CI Var | ✅ 已有 |
| `ARGOCD_TEST_TOKEN` | Group CI Var | ✅ 已有 |
| `ECR_PROD_ADDR` | Group CI Var | ✅ 已有 |
| `PROJECT_ID` | Project CI Var | ✅ 每项目独立 |
| Shore Repo Read | GitLab Token Access | **需配置** |
