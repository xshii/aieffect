#!/usr/bin/env bash
# ===========================================================================
# aieffect 一键部署脚本（无 Docker）
#
# 用法:
#   ./deploy.sh                        # 本地部署（gunicorn 后台）
#   ./deploy.sh --remote user@host     # 远程服务器部署（SSH）
#   ./deploy.sh --tunnel user@host     # SSH 端口转发（开发用）
#   ./deploy.sh --supervisor            # 安装 supervisord 托管
#   ./deploy.sh --stop                 # 停止本地 gunicorn
#   ./deploy.sh --status               # 查看运行状态
#   ./deploy.sh --test                 # 测试通过后再部署
#
# 环境变量:
#   AIEFFECT_PORT      - 监听端口（默认 8888）
#   AIEFFECT_WORKERS   - gunicorn 工作进程数（默认自动）
#   AIEFFECT_DIR       - 远程安装目录（默认 /opt/aieffect）
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${AIEFFECT_PORT:-8888}"
CUSTOM_PORT="${AIEFFECT_PORT:+true}"  # 非空表示用户指定了端口
INSTALL_DIR="${AIEFFECT_DIR:-/opt/aieffect}"
PID_FILE="/tmp/aieffect.pid"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# 指定了非默认端口时，提示需要端口转发
hint_port_forward() {
    if [ "${CUSTOM_PORT:-}" = "true" ]; then
        warn "已指定端口 $PORT，Web 看板需通过端口转发访问:"
        info "  ssh -L ${PORT}:localhost:${PORT} user@<remote-host>"
        info "  然后浏览器打开 http://localhost:${PORT}"
    fi
}

# ── 前置检查 ──────────────────────────────────────────────────────────────

require_python() {
    local py=""
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            py="$cmd"
            break
        fi
    done
    if [ -z "$py" ]; then
        error "未找到 Python 3.10+"; exit 1
    fi
    local minor
    minor=$($py -c "import sys; print(sys.version_info.minor)")
    if [ "$minor" -lt 10 ]; then
        error "需要 Python 3.10+，当前为 3.$minor"; exit 1
    fi
    echo "$py"
}

ensure_venv() {
    local py="$1"
    if [ ! -d "venv" ]; then
        info "创建虚拟环境..."
        "$py" -m venv venv
    fi
    # shellcheck disable=SC1091
    source venv/bin/activate
}

install_deps() {
    info "安装项目依赖..."
    pip install --upgrade pip -q
    pip install -e ".[dev]" gunicorn -q
    info "依赖安装完成。"
}

ensure_dirs() {
    mkdir -p data results deps/cache deps/snapshots configs
    if [ ! -f configs/default.yml ]; then
        echo "{}" > configs/default.yml
        warn "已创建空的 configs/default.yml"
    fi
}

# ── 本地部署 ──────────────────────────────────────────────────────────────

deploy_local() {
    local py
    py=$(require_python)
    ensure_venv "$py"
    install_deps
    ensure_dirs

    # 停止已有进程
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        info "停止旧进程..."
        kill "$(cat "$PID_FILE")" 2>/dev/null || true
        sleep 1
    fi

    info "启动 gunicorn (port=$PORT)..."
    GUNICORN_BIND="0.0.0.0:$PORT" \
        gunicorn \
        --config deploy/gunicorn.conf.py \
        --daemon \
        --pid "$PID_FILE" \
        framework.web.app:app

    info "部署完成！"
    info "  看板地址:   http://localhost:${PORT}"
    info "  停止服务:   ./deploy.sh --stop"
    info "  查看状态:   ./deploy.sh --status"
    hint_port_forward
}

# ── 远程部署 ──────────────────────────────────────────────────────────────

deploy_remote() {
    local target="$1"
    info "部署到远程服务器: $target"

    info "同步代码到 $target:$INSTALL_DIR ..."
    ssh "$target" "mkdir -p $INSTALL_DIR"
    rsync -az --delete \
        --exclude .git \
        --exclude __pycache__ \
        --exclude '*.pyc' \
        --exclude .pytest_cache \
        --exclude .mypy_cache \
        --exclude htmlcov \
        --exclude venv \
        ./ "$target:$INSTALL_DIR/"

    info "在远程服务器安装并启动..."
    ssh "$target" bash <<REMOTE_SCRIPT
set -euo pipefail
cd "$INSTALL_DIR"

# 确保 Python
PY=""
for cmd in python3 python; do
    if command -v "\$cmd" &>/dev/null; then PY="\$cmd"; break; fi
done
if [ -z "\$PY" ]; then echo "ERROR: Python 3.10+ not found"; exit 1; fi

# venv + 依赖
if [ ! -d venv ]; then "\$PY" -m venv venv; fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -e ".[dev]" gunicorn -q

# 创建目录
mkdir -p data results deps/cache deps/snapshots configs
[ -f configs/default.yml ] || echo "{}" > configs/default.yml

# 停旧启新
PID_FILE="/tmp/aieffect.pid"
if [ -f "\$PID_FILE" ] && kill -0 "\$(cat \$PID_FILE)" 2>/dev/null; then
    kill "\$(cat \$PID_FILE)" 2>/dev/null || true
    sleep 1
fi

GUNICORN_BIND="0.0.0.0:$PORT" \
    gunicorn \
    --config deploy/gunicorn.conf.py \
    --daemon \
    --pid "\$PID_FILE" \
    framework.web.app:app

echo "aieffect 已启动 (port=$PORT)"
REMOTE_SCRIPT

    info "远程部署完成！"
    warn "远程服务需通过端口转发访问 Web 看板:"
    info "  ssh -L ${PORT}:localhost:${PORT} $target"
    info "  然后浏览器打开 http://localhost:${PORT}"
}

# ── SSH 端口转发 ──────────────────────────────────────────────────────────

tunnel_to_remote() {
    local target="$1"
    info "建立 SSH 隧道: 本地 $PORT -> $target:$PORT"
    info "按 Ctrl+C 关闭隧道"
    info "看板地址: http://localhost:${PORT}"
    ssh -N -L "${PORT}:localhost:${PORT}" "$target"
}

# ── supervisord 安装 ──────────────────────────────────────────────────────

install_supervisor() {
    # 确保 supervisor 已安装
    if ! command -v supervisord &>/dev/null; then
        info "安装 supervisor..."
        pip install supervisor -q 2>/dev/null || sudo pip install supervisor -q
    fi

    # 确定配置目录
    local conf_dir="/etc/supervisor/conf.d"
    if [ ! -d "$conf_dir" ]; then
        conf_dir="/etc/supervisord.d"
    fi

    if [ ! -d "$conf_dir" ]; then
        error "未找到 supervisor 配置目录（/etc/supervisor/conf.d 或 /etc/supervisord.d）"
        error "请先安装 supervisor: apt install supervisor 或 yum install supervisor"
        exit 1
    fi

    # 创建日志目录
    mkdir -p "$INSTALL_DIR/data/logs"

    # 生成配置（替换路径变量）
    local conf_file="$conf_dir/aieffect.conf"
    info "安装 supervisor 配置到 $conf_file ..."
    sed "s|/opt/aieffect|$INSTALL_DIR|g" deploy/supervisord.conf | \
        sudo tee "$conf_file" > /dev/null

    # 重载并启动
    sudo supervisorctl reread
    sudo supervisorctl update
    sudo supervisorctl restart aieffect 2>/dev/null || true

    info "supervisord 托管已安装！"
    info "  查看状态: sudo supervisorctl status aieffect"
    info "  查看日志: tail -f $INSTALL_DIR/data/logs/aieffect.log"
    info "  停止服务: sudo supervisorctl stop aieffect"
    info "  重启服务: sudo supervisorctl restart aieffect"
    hint_port_forward
}

# ── 停止 / 状态 ──────────────────────────────────────────────────────────

stop_local() {
    if sudo supervisorctl status aieffect &>/dev/null 2>&1; then
        info "停止 supervisor 托管服务..."
        sudo supervisorctl stop aieffect
    elif [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        info "停止 gunicorn (PID=$(cat "$PID_FILE"))..."
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
    else
        warn "未发现运行中的服务。"
        return
    fi
    info "已停止。"
}

show_status() {
    if sudo supervisorctl status aieffect 2>/dev/null | grep -q RUNNING; then
        sudo supervisorctl status aieffect
        info "看板地址: http://localhost:${PORT}"
        info "查看日志: tail -f ${INSTALL_DIR}/data/logs/aieffect.log"
    elif [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        info "gunicorn 运行中 (PID=$(cat "$PID_FILE"), port=$PORT)"
        info "看板地址: http://localhost:${PORT}"
    else
        warn "无运行中的服务"
    fi
}

run_tests() {
    local py
    py=$(require_python)
    ensure_venv "$py"
    install_deps

    info "运行测试..."
    python -m pytest tests/ -q

    info "运行 lint..."
    python -m ruff check framework/ tests/

    info "全部通过！"
}

# ── 主入口 ────────────────────────────────────────────────────────────────

case "${1:-}" in
    --remote)
        [ -z "${2:-}" ] && { error "用法: ./deploy.sh --remote user@host"; exit 1; }
        deploy_remote "$2"
        ;;
    --tunnel)
        [ -z "${2:-}" ] && { error "用法: ./deploy.sh --tunnel user@host"; exit 1; }
        tunnel_to_remote "$2"
        ;;
    --supervisor)
        install_supervisor
        ;;
    --stop)
        stop_local
        ;;
    --status)
        show_status
        ;;
    --test)
        run_tests
        deploy_local
        ;;
    --help|-h)
        head -19 "$0" | tail -16
        ;;
    *)
        deploy_local
        ;;
esac
