#!/usr/bin/env bash
# Jenkins Agent 节点初始化脚本
# 在每台执行 EDA 仿真的 agent 机器上运行此脚本
set -euo pipefail

echo "=== aieffect Jenkins Agent 初始化 ==="

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "错误: 未找到 Python 3，请先安装 Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python 版本: ${PYTHON_VERSION}"

# 2. 检查 EDA 工具（可选，未找到仅警告）
for tool in vcs xrun verilator; do
    if command -v "$tool" &>/dev/null; then
        echo "已找到: $tool ($(command -v "$tool"))"
    else
        echo "警告: $tool 不在 PATH 中"
    fi
done

# 3. 检查 License
if [ -z "${LM_LICENSE_FILE:-}" ]; then
    echo "警告: LM_LICENSE_FILE 未设置，EDA 工具可能无法使用。"
else
    echo "License: ${LM_LICENSE_FILE}"
fi

# 4. 安装 Python 依赖
echo "安装 Python 依赖..."
python3 -m pip install --quiet -e ".[dev]"

# 5. 验证框架可加载
python3 -c "import framework; print(f'aieffect {framework.__version__} 加载成功')"

echo "=== 初始化完成 ==="
