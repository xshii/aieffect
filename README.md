# aieffect — AI Chip Verification Efficiency Integration Platform

AI 芯片验证效率集成平台，统一管理 CI/CD、用例执行框架、周边依赖和测试数据。

**本仓库不包含任何模型代码或 RTL 设计。**

## 目录结构

```
aieffect/
├── .github/workflows/    GitHub Actions CI/CD
├── cicd/                  CI/CD 扩展配置（Jenkins 等）
├── framework/             用例执行框架（核心）
│   ├── core/              引擎层：runner / scheduler / reporter / collector
│   ├── plugins/           插件扩展点
│   └── utils/             公共工具
├── deps/                  周边依赖管理
├── testdata/              测试数据管理
├── configs/               全局配置
├── scripts/               常用脚本
├── tests/                 框架自身单元测试
└── docs/                  文档
```

## 快速开始

```bash
# 1. 安装依赖
make setup

# 2. 运行 lint
make lint

# 3. 运行单元测试
make test

# 4. 运行回归
make regression
```

## 设计原则

- **不含模型代码** — 模型通过依赖声明引入，本仓库只管验证工具链
- **命令驱动** — 用例通过 shell 命令执行，不绑定特定仿真器
- **CI 平台无关** — 核心逻辑在 Makefile + Python，CI 配置只是薄胶水层
- **可复现** — 所有依赖版本锁定，测试数据有版本追溯

## CI/CD

- GitHub Actions: 见 `.github/workflows/`
- Jenkins: 见 `cicd/jenkins/`（含安装指南和必装插件）

## License

Internal use only.
