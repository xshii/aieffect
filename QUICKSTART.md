# aieffect Quickstart

> 5 分钟上手 AI 芯片验证效率集成平台

---

## 环境要求

- Python >= 3.10
- pip

---

## 第 1 步：安装

```bash
git clone <repo-url> && cd aieffect
make setup          # 等同于 pip install -e ".[dev]"
```

验证安装：

```bash
aieffect --help
```

---

## 第 2 步：创建测试套件

在 `testdata/configs/` 下新建 `smoke.yml`：

```yaml
suite_name: smoke
description: "冒烟测试套件"

testcases:
  - name: sanity_check
    timeout: 60
    tags: [smoke, sanity]
    args:
      cmd: "echo '健全性测试通过'"

  - name: dma_basic
    timeout: 600
    tags: [smoke, dma]
    args:
      cmd: "echo 'DMA 基础测试通过'"
```

> 将 `echo ...` 替换为实际的仿真命令，如 `vcs -f run.f +UVM_TESTNAME=sanity`

---

## 第 3 步：执行回归

```bash
# 单线程执行
aieffect run smoke

# 4 并行执行
aieffect run smoke -p 4
```

执行完毕后，结果自动写入 `results/` 目录。

---

## 第 4 步：查看结果

```bash
# 终端查看 HTML 报告
aieffect report results --format html

# 启动 Web 看板（浏览器访问 http://127.0.0.1:8888）
aieffect dashboard --port 8888
```

---

## 第 5 步：注册独立用例

不写套件文件也可以直接注册用例：

```bash
aieffect cases add my_test \
  --cmd "vcs -f run.f" \
  --tag smoke \
  --timeout 600
```

查看已注册用例：

```bash
aieffect cases list
```

---

## 下一步

| 想做什么 | 参考 |
|---------|------|
| 管理依赖包 | `USAGE.md` § 3 依赖管控 |
| 锁定版本快照 | `USAGE.md` § 4 版本快照 |
| 查询历史通过率 | `USAGE.md` § 5 执行历史 |
| 日志规则检查 | `USAGE.md` § 7 日志检查 |
| 生产部署 | `USAGE.md` § 10 部署 |
| Jenkins 对接 | `USAGE.md` § 11 CI 集成 |
| REST API 全览 | `USAGE.md` § 9 Web 看板 & API |

完整文档见 [USAGE.md](USAGE.md)。
