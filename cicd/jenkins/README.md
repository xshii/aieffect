# Jenkins 部署指南

本文档覆盖 Jenkins 的安装、必装插件、以及与 aieffect 集成的配置方法。

## 1. 安装 Jenkins

### 方式一：Docker 安装（推荐，快速搭建）

```bash
# 拉取 LTS 镜像
docker pull jenkins/jenkins:lts-jdk17

# 启动（数据持久化到 jenkins_home 卷）
docker run -d \
  --name jenkins \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  jenkins/jenkins:lts-jdk17

# 获取初始密码
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

访问 `http://<your-host>:8080`，输入初始密码，完成安装向导。

### 方式二：系统包安装（CentOS/RHEL）

```bash
# 导入 GPG key
sudo rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key

# 添加 yum repo
sudo tee /etc/yum.repos.d/jenkins.repo <<'EOF'
[jenkins]
name=Jenkins-stable
baseurl=https://pkg.jenkins.io/redhat-stable/
gpgcheck=1
gpgkey=https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key
EOF

# 安装
sudo yum install -y java-17-openjdk jenkins

# 启动
sudo systemctl enable --now jenkins

# 获取初始密码
sudo cat /var/lib/jenkins/secrets/initialAdminPassword
```

### 方式三：系统包安装（Ubuntu/Debian）

```bash
# 导入 GPG key 和 apt 源
curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key | \
  sudo tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null

echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] \
  https://pkg.jenkins.io/debian-stable binary/" | \
  sudo tee /etc/apt/sources.list.d/jenkins.list > /dev/null

# 安装
sudo apt update
sudo apt install -y openjdk-17-jre jenkins

# 启动
sudo systemctl enable --now jenkins
```

## 2. 必装插件

安装后进入 **Manage Jenkins → Plugins → Available plugins**，搜索并安装以下插件：

### 核心必装

| 插件名 | 用途 | 为什么需要 |
|--------|------|-----------|
| **Pipeline** | 流水线即代码 | Jenkinsfile 执行引擎，没有这个 Jenkins 只能用 freestyle job |
| **Git** | Git SCM 支持 | 拉取代码，轮询变更 |
| **Credentials Binding** | 凭据管理 | 安全管理 Git token、SSH key 等敏感信息 |
| **Timestamper** | 日志时间戳 | 回归跑几个小时，没有时间戳根本无法定位问题 |
| **Build Timeout** | 构建超时 | 防止仿真挂死占用 agent 资源 |

### 强烈推荐

| 插件名 | 用途 | 为什么需要 |
|--------|------|-----------|
| **JUnit** | 测试结果解析 | 解析 JUnit XML 报告，在 Jenkins 仪表盘展示通过率趋势图 |
| **HTML Publisher** | HTML 报告发布 | 发布 aieffect 生成的 HTML 覆盖率/回归报告 |
| **Pipeline Stage View** | 阶段可视化 | 直观看到每个阶段的执行状态和耗时 |
| **Email Extension** | 邮件通知 | 回归失败时发送邮件通知，支持自定义模板 |
| **Workspace Cleanup** | 工作区清理 | 仿真产物动辄几十 GB，不清理磁盘必炸 |
| **Throttle Concurrent Builds** | 并发控制 | 控制 EDA license 并发使用量，避免 license 耗尽 |

### 企业内网场景推荐

| 插件名 | 用途 | 为什么需要 |
|--------|------|-----------|
| **SSH Agent** | SSH 凭据转发 | 连接内网 LSF/SGE 集群提交仿真任务 |
| **Parameterized Trigger** | 参数化触发 | 支持不同 suite/simulator 组合触发回归 |
| **Matrix Project** | 矩阵构建 | 同时跑多个仿真器 × 多个 suite 的组合矩阵 |
| **Lockable Resources** | 资源锁定 | 锁定稀缺 EDA license 资源，避免竞争 |
| **LDAP / Active Directory** | 认证集成 | 对接企业内网 LDAP，统一权限管理 |
| **Role-based Authorization** | 权限分级 | 不同团队看不同 pipeline，保护敏感项目 |

### 可选增强

| 插件名 | 用途 | 为什么需要 |
|--------|------|-----------|
| **Blue Ocean** | 现代化 UI | 更好看的流水线可视化（但已停止积极开发） |
| **Prometheus Metrics** | 监控指标 | 暴露 Jenkins 指标到 Prometheus，接入 Grafana 看板 |
| **Artifact Manager on S3** | 制品存储 | 大量回归报告存到 S3/MinIO，不占 Jenkins 本地磁盘 |
| **Slack Notification** | Slack 通知 | 如果团队用 Slack 沟通 |

## 3. 一键安装插件（CLI 方式）

如果不想在 UI 上一个个点，可以用 Jenkins CLI 批量安装：

```bash
# 进入 Jenkins 容器（Docker 方式）
docker exec -it jenkins bash

# 使用 jenkins-plugin-cli 批量安装
jenkins-plugin-cli --plugins \
  workflow-aggregator \
  git \
  credentials-binding \
  timestamper \
  build-timeout \
  junit \
  htmlpublisher \
  pipeline-stage-view \
  email-ext \
  ws-cleanup \
  throttle-concurrents \
  ssh-agent \
  parameterized-trigger \
  matrix-project \
  lockable-resources
```

对应的 `plugins.txt`（用于 Docker 镜像构建）：

```
workflow-aggregator
git
credentials-binding
timestamper
build-timeout
junit
htmlpublisher
pipeline-stage-view
email-ext
ws-cleanup
throttle-concurrents
ssh-agent
parameterized-trigger
matrix-project
lockable-resources
```

## 4. 配置 Jenkins 连接本仓库

### 4.1 创建 Pipeline Job

1. **New Item** → 输入名称 → 选择 **Pipeline**
2. **Pipeline** 区域：
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: 填入本仓库地址
   - Script Path: `cicd/jenkins/Jenkinsfile`
3. **Build Triggers**（按需选择）：
   - Poll SCM: `H/5 * * * *`（每 5 分钟检测变更）
   - 或配合 GitHub Webhook 触发

### 4.2 配置 Agent 节点

芯片验证需要 agent 节点上安装 EDA 工具：

1. **Manage Jenkins** → **Nodes** → **New Node**
2. 设置 label 为 `eda`（与 Jenkinsfile 中 `agent { label 'eda' }` 对应）
3. Launch method: 选择 **Launch agents via SSH**
4. 确保 agent 机器上有：
   - Python 3.10+
   - EDA 工具（VCS/Xcelium）和 license 环境变量
   - 足够的磁盘空间（建议 500GB+）

### 4.3 配置 EDA License

在 **Manage Jenkins** → **System** → **Global properties** → **Environment variables** 中添加：

```
LM_LICENSE_FILE = <port>@<license-server>
VCS_HOME        = /opt/synopsys/vcs/<version>
XCELIUM_HOME    = /opt/cadence/xcelium/<version>
```

## 5. Jenkins vs GitHub Actions 在本仓库中的分工

| 场景 | 推荐平台 | 原因 |
|------|---------|------|
| PR 门禁（lint/test） | GitHub Actions | 无需 EDA 工具，GitHub 托管 runner 即可 |
| 框架单元测试 | GitHub Actions | 同上 |
| 芯片回归仿真 | Jenkins (内网) | 需要 EDA 工具 + license server |
| 夜间全量回归 | Jenkins (内网) | 长时间运行 + 大量磁盘 I/O |
| 覆盖率合并 | Jenkins (内网) | 依赖 EDA 覆盖率工具（urg/imc） |

两者通过 `Makefile` 共享同一套执行逻辑，CI 配置只是薄胶水层。
