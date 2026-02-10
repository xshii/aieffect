# aieffect — AI 芯片验证效率集成平台

统一管理 CI/CD、用例执行框架、周边依赖和测试数据。

**本仓库不包含任何模型代码或 RTL 设计。**

## 目录结构

```
aieffect/
├── .github/workflows/    GitHub Actions CI/CD
├── cicd/                  CI/CD 扩展配置（Jenkins 等）
├── framework/             用例执行框架（核心）
│   ├── core/              引擎层：runner / scheduler / reporter / collector / dep_manager
│   ├── web/               Flask 轻量看板
│   └── utils/             公共工具（日志等）
├── deps/                  依赖统一清单（manifest.yml）+ 缓存 + LFS 包
├── testdata/              测试数据管理
├── configs/               全局配置
├── tests/                 框架自身单元测试
└── docs/                  文档
```

## 快速开始

```bash
# 1. 安装依赖
make setup

# 2. 运行 lint + 单元测试
make lint
make test

# 3. 运行回归
aieffect run default -p 4

# 4. 生成报告
aieffect report results -f html

# 5. 启动 Web 看板
aieffect dashboard --port 8888
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `aieffect run <suite>` | 运行测试套件 |
| `aieffect report <dir>` | 生成测试报告（html/json/junit） |
| `aieffect fetch` | 拉取全部依赖包 |
| `aieffect deps` | 列出已注册的依赖包 |
| `aieffect upload <name> <version> <path>` | 上传包到 Git LFS |
| `aieffect dashboard` | 启动 Web 看板 |
| `aieffect apply-deps` | 应用依赖版本覆盖（Jenkins 用） |

## 设计原则

- **不含模型代码** — 模型通过依赖声明引入，本仓库只管验证工具链
- **命令驱动** — 用例通过 shell 命令执行，不绑定特定仿真器
- **CI 平台无关** — 核心逻辑在 Makefile + Python，CI 配置只是薄胶水层
- **可复现** — 所有依赖版本锁定在 `deps/manifest.yml`

## CI/CD

- GitHub Actions: 见 `.github/workflows/`
- Jenkins: 见 `cicd/jenkins/`（含安装指南和必装插件）

## License

Internal use only.
