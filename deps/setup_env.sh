#!/usr/bin/env bash
# aieffect 一键环境初始化脚本
# 使用方式: source deps/setup_env.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== aieffect 环境初始化 ==="

# 1. 创建 Python 虚拟环境
VENV_DIR="${PROJECT_ROOT}/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi
source "${VENV_DIR}/bin/activate"

# 2. 安装依赖
pip install --quiet -e "${PROJECT_ROOT}[dev]"

# 3. 添加项目根目录到 PYTHONPATH
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

# 4. 加载 EDA 工具路径（按实际环境修改）
# 取消注释并调整为你的环境:
# export VCS_HOME="/opt/synopsys/vcs/U-2023.03-SP2"
# export PATH="${VCS_HOME}/bin:${PATH}"
# export XCELIUM_HOME="/opt/cadence/xcelium/23.09"
# export PATH="${XCELIUM_HOME}/bin:${PATH}"
# export LM_LICENSE_FILE="27000@lic-server:5280@lic-server"

echo "aieffect 环境就绪。Python: $(python3 --version)"
