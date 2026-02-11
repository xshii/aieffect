# aieffect 使用指南

> AI 芯片验证效率集成平台 — 用例管理、回归执行、依赖管控、结果看板一体化

---

## 快速开始

```bash
# 1. 安装
make setup

# 2. 注册用例
aieffect cases add my_test --cmd "vcs -f run.f" --tag smoke --timeout 600

# 3. 执行回归
aieffect run default -p 4

# 4. 查看结果
aieffect report results --format html
aieffect dashboard --port 8888
```

---

## 功能总览

| 能力 | CLI 命令 | REST API | 说明 |
|------|---------|----------|------|
| 回归执行 | `aieffect run` | `POST /api/run` | 套件/用例/并行/参数/快照 |
| 用例管理 | `aieffect cases` | `/api/cases` | CRUD + 环境绑定 + 参数模式 |
| 依赖管控 | `aieffect fetch/deps/resolve` | `GET /api/deps` | 本地优先 + 4 种来源 |
| 版本快照 | `aieffect snapshot` | `/api/snapshots` | 锁定/恢复/对比 |
| 执行历史 | `aieffect history` | `/api/history` | 查询/统计/外部录入 |
| 报告生成 | `aieffect report` | — | HTML / JSON / JUnit |
| 日志检查 | `aieffect check-log` | `POST /api/check-log` | 正则规则匹配 |
| 资源管理 | `aieffect resource` | `GET /api/resource` | 自管理 / 外部 API |
| 存储对接 | — | `/api/storage` | 本地文件 / 远端 REST |
| Web 看板 | `aieffect dashboard` | `GET /` | 全功能 Web UI |
| 一键部署 | `./deploy.sh` | — | local / remote / supervisor |

---

## 1. 回归执行

### 定义套件

创建 `testdata/configs/smoke.yml`：

```yaml
cases:
  - name: sanity_check
    cmd: "vcs -f sanity.f +UVM_TESTNAME=sanity"
    timeout: 600
    tags: [smoke, sanity]

  - name: full_regression
    cmd: "vcs -f regr.f +seed={seed}"
    timeout: 3600
    tags: [full]
    params:
      seed: "12345"
```

### 执行

```bash
# 执行 smoke 套件，4 并行
aieffect run smoke -p 4

# 指定环境 + 快照
aieffect run smoke -e prod --snapshot snap_20260210

# 运行时覆盖参数
aieffect run smoke --param seed=99999

# 只跑指定用例
aieffect run smoke --case sanity_check --case dma_test

# 使用自定义配置
aieffect run smoke -c configs/custom.yml
```

### 外部仓库用例

```bash
# 注册外部 Git 仓库用例
aieffect cases add ext_test \
  --cmd "make run TEST=my_test" \
  --repo-url https://github.com/team/tb.git \
  --repo-ref main \
  --repo-setup "pip install -r requirements.txt" \
  --repo-build "make compile"
```

执行时自动：`git clone` → 安装依赖 → 编译 → 运行

---

## 2. 用例管理

```bash
# 注册用例
aieffect cases add dma_test \
  --cmd "xrun -f dma.f" \
  --desc "DMA 通道传输测试" \
  --tag dma --tag regression \
  --timeout 1800 \
  --env fpga --env sim

# 列出所有用例
aieffect cases list

# 按标签过滤
aieffect cases list --tag smoke

# 按环境过滤
aieffect cases list --env fpga

# 删除用例
aieffect cases remove dma_test

# 添加执行环境
aieffect cases env-add fpga --desc "FPGA 验证环境"
aieffect cases env-add sim --desc "仿真环境"
aieffect cases env-list
```

---

## 3. 依赖管控

### 依赖清单 (`deps/manifest.yml`)

```yaml
python: "3.10"

eda_tools:
  vcs:
    version: "U-2023.03-SP2"
    install_path: "/opt/synopsys/vcs"
    env_vars:
      VCS_HOME: "{path}"
      PATH: "{path}/bin:$PATH"

packages:
  model_lib:
    owner: "AI 模型团队"
    version: "v2.1.0"
    source: local           # local | api | lfs | url
    base_path: "/shared/libs/model_lib"
    checksum_sha256: "abc123..."
```

### 操作

```bash
# 查看所有依赖
aieffect deps

# 拉取全部依赖（本地优先，缺失时远程下载）
aieffect fetch

# 拉取指定包指定版本
aieffect fetch --name model_lib --version v2.2.0

# 查看本地已有版本
aieffect versions model_lib

# 解析本地路径（不触发下载）
aieffect resolve model_lib --version v2.1.0

# 批量覆盖版本（CI 场景）
aieffect apply-deps --override versions.yml
aieffect apply-deps --dep-name model_lib --dep-version v2.2.0
```

---

## 4. 版本快照

```bash
# 创建快照（锁定当前所有依赖版本）
aieffect snapshot create --desc "Release v1.0 候选"

# 列出所有快照
aieffect snapshot list

# 恢复到某个快照
aieffect snapshot restore 20260210_143022

# 对比两个快照差异
aieffect snapshot diff 20260210_143022 20260208_091500
```

---

## 5. 执行历史

```bash
# 查看最近记录
aieffect history list --limit 10

# 按套件过滤
aieffect history list --suite smoke

# 查看某个用例的通过率统计
aieffect history case dma_test
```

通过 API 录入外部结果（非 aieffect 执行的测试）：

```bash
curl -X POST http://localhost:8888/api/history/submit \
  -H "Content-Type: application/json" \
  -d '{"suite":"ext_test","results":[{"name":"t1","status":"passed","duration":12.5}]}'
```

---

## 6. 报告生成

```bash
# HTML 报告（默认）
aieffect report results

# JUnit XML（对接 Jenkins）
aieffect report results --format junit

# JSON 格式
aieffect report results --format json
```

---

## 7. 日志检查

### 规则定义 (`configs/log_rules.yml`)

```yaml
rules:
  - name: simulation_complete
    pattern: "\\$finish|Simulation complete"
    type: required           # required = 必须出现, forbidden = 不能出现
    description: "仿真正常结束标志"

  - name: no_fatal_error
    pattern: "FATAL|Fatal error"
    type: forbidden
    description: "不允许出现致命错误"
```

### 使用

```bash
# 检查日志文件
aieffect check-log sim.log

# 使用自定义规则
aieffect check-log sim.log --rules my_rules.yml
```

通过 API 检查：

```bash
# 上传文件
curl -X POST http://localhost:8888/api/check-log \
  -F "file=@sim.log"

# 提交文本
curl -X POST http://localhost:8888/api/check-log \
  -H "Content-Type: application/json" \
  -d '{"text":"... log content ...","source":"my_sim"}'
```

---

## 8. 配置说明

`configs/default.yml`：

```yaml
# 目录
suite_dir: "testdata/configs"       # 套件定义目录
result_dir: "results"               # 结果输出目录

# 执行
parallel: 1                          # 默认并行度
max_workers: 8                       # 最大 worker 数
default_timeout: 3600                # 默认超时（秒）

# 日志
logging:
  level: "INFO"
  json_output: false                 # CI 中设为 true

# 资源管理
resource:
  mode: "self"                       # self = 自管理, api = 外部 API
  max_workers: 8
  api_url: ""                        # 外部资源 API 地址

# 存储
storage:
  backend: "local"                   # local = 本地文件, remote = REST API
  local_dir: "data/storage"
  remote:
    api_url: ""
    cache_dir: "data/cache"
    cache_days: 7                    # 缓存保留天数
```

---

## 9. Web 看板 & REST API

```bash
# 启动
aieffect dashboard --port 8888

# 或通过 gunicorn 生产部署
./deploy.sh
```

### API 示例

```bash
# 查看回归结果
curl http://localhost:8888/api/results

# 触发回归
curl -X POST http://localhost:8888/api/run \
  -H "Content-Type: application/json" \
  -d '{"suite":"smoke","parallel":4}'

# 用例 CRUD
curl http://localhost:8888/api/cases
curl http://localhost:8888/api/cases/dma_test
curl -X POST http://localhost:8888/api/cases \
  -d '{"name":"new_test","cmd":"make run"}'
curl -X DELETE http://localhost:8888/api/cases/old_test

# 上传依赖包
curl -X POST http://localhost:8888/api/deps/upload \
  -F "name=model_lib" -F "version=v2.2.0" -F "file=@model_lib.tar.gz"

# 快照管理
curl http://localhost:8888/api/snapshots
curl -X POST http://localhost:8888/api/snapshots \
  -d '{"description":"pre-release"}'

# 资源状态
curl http://localhost:8888/api/resource
```

---

## 10. 部署

```bash
# 本地一键部署（gunicorn 后台）
./deploy.sh

# 远程服务器部署
./deploy.sh --remote user@10.0.0.100

# 安装 supervisord 托管（自动重启 + 日志管理）
./deploy.sh --supervisor

# SSH 端口转发（开发用）
./deploy.sh --tunnel user@10.0.0.100

# 管理
./deploy.sh --stop
./deploy.sh --status

# 自定义端口和目录
AIEFFECT_PORT=9999 AIEFFECT_DIR=/opt/myapp ./deploy.sh
```

Supervisor 管理：
```bash
sudo supervisorctl status aieffect
sudo supervisorctl restart aieffect
tail -f /opt/aieffect/data/logs/aieffect.log
```

---

## 11. Jenkins CI 集成

Jenkinsfile 已配置 3 种触发模式：

| 模式 | 触发方式 | 套件 |
|------|---------|------|
| 定时 smoke | 工作日 02:00 | smoke |
| 定时 full | 周日 00:00 | full |
| 依赖变更 | 上游 Job 通知 | default |
| 手动 | Jenkins UI 参数化触发 | 可选 |

---

## 12. Makefile 速查

```bash
make setup          # 安装依赖
make lint           # ruff 检查
make typecheck      # mypy 类型检查
make test           # 运行测试
make test-cov       # 覆盖率报告
make regression     # 执行回归套件
make report         # 生成报告
make dashboard      # 启动看板
make deploy         # 本地部署
make deploy-remote TARGET=user@host  # 远程部署
make deploy-stop    # 停止服务
make deploy-status  # 查看状态
make clean          # 清理临时文件
```

---

## 目录结构

```
aieffect/
├── framework/
│   ├── cli.py              # CLI 入口（26 个命令）
│   ├── core/               # 核心模块
│   │   ├── runner.py       #   套件执行编排
│   │   ├── scheduler.py    #   并行调度器
│   │   ├── pipeline.py     #   结果处理管线（观察者模式）
│   │   ├── config.py       #   配置中心（单例）
│   │   ├── models.py       #   数据模型 (Case/TaskResult/SuiteResult)
│   │   ├── exceptions.py   #   异常体系
│   │   ├── dep_manager.py  #   依赖管理（4 种来源）
│   │   ├── case_manager.py #   用例 CRUD + 环境绑定
│   │   ├── history.py      #   执行历史
│   │   ├── snapshot.py     #   版本快照
│   │   ├── reporter.py     #   报告生成（策略模式）
│   │   ├── log_checker.py  #   日志规则匹配
│   │   ├── resource.py     #   资源繁忙度管理
│   │   ├── storage.py      #   存储抽象层
│   │   └── collector.py    #   结果持久化
│   ├── services/           # 服务层
│   │   ├── run_service.py  #   统一执行服务
│   │   └── case_service.py #   用例操作服务
│   ├── utils/              # 工具层
│   │   ├── yaml_io.py      #   YAML 原子读写
│   │   ├── net.py          #   URL 安全校验
│   │   └── logger.py       #   日志配置
│   └── web/
│       └── app.py          # Flask REST API（17 个端点）
├── configs/                # 配置文件
├── deps/                   # 依赖管理
├── data/                   # 运行时数据
├── testdata/configs/       # 套件定义
├── results/                # 测试结果
├── tests/                  # 154 个单元测试
├── deploy.sh               # 部署脚本
├── deploy/                 # gunicorn + supervisor 配置
├── cicd/jenkins/           # Jenkins 流水线
├── Makefile
└── pyproject.toml
```
