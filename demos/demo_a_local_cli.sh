#!/bin/bash
# =========================================================================
#  Demo A — 本地 PC 命令行完整流程
# =========================================================================
#
#  场景描述:
#    1. 在本地 PC 上运行功能仿真器（EDA 环境）
#    2. 所有依赖版本锁定到配置套 20250206B003
#    3. 将 rtl_core 仓库的分支覆盖为 br_fix_timing_closure
#    4. 编译打包后在本地执行选定用例
#    5. 分析结果并上传日志到远程服务器保存
#
#  使用方式:
#    chmod +x demos/demo_a_local_cli.sh
#    ./demos/demo_a_local_cli.sh
#
# =========================================================================

set -euo pipefail

echo "============================================="
echo "  Demo A: 本地 PC CLI 完整验证流程"
echo "============================================="
echo ""

# ----- 可配置参数 -----
SNAPSHOT_ID="20250206B003"
REPO_NAME="rtl_core"
REPO_URL="https://git.company.com/chip/rtl_core.git"
REPO_BRANCH_OVERRIDE="br_fix_timing_closure"
BUILD_NAME="rtl_build"
SUITE_NAME="smoke"
CASE_NAMES=("sanity_check" "basic_func")
UPLOAD_TARGET="ci@10.0.1.100:/data/results"
SSH_KEY="~/.ssh/id_rsa"

echo ">>> 配置参数:"
echo "    快照 ID:        $SNAPSHOT_ID"
echo "    仓库:           $REPO_NAME ($REPO_URL)"
echo "    分支覆盖:       $REPO_BRANCH_OVERRIDE"
echo "    构建名称:       $BUILD_NAME"
echo "    测试套:         $SUITE_NAME"
echo "    选定用例:       ${CASE_NAMES[*]}"
echo "    上传目标:       $UPLOAD_TARGET"
echo ""


# =========================================================================
# 步骤 1: 锁定依赖版本 — 恢复快照 20250206B003
# =========================================================================
echo ">>> [1/8] 恢复依赖快照 $SNAPSHOT_ID ..."

aieffect snapshot restore "$SNAPSHOT_ID"

echo "    快照已恢复，所有依赖版本已锁定。"
echo ""


# =========================================================================
# 步骤 2: 注册代码仓 — 设置分支覆盖
# =========================================================================
echo ">>> [2/8] 注册代码仓 $REPO_NAME (分支: $REPO_BRANCH_OVERRIDE) ..."

# 先移除旧注册（如有）
aieffect repo remove "$REPO_NAME" 2>/dev/null || true

# 重新注册，ref 指向需要验证的分支
aieffect repo add "$REPO_NAME" \
    --type git \
    --url "$REPO_URL" \
    --ref "$REPO_BRANCH_OVERRIDE" \
    --setup-cmd "pip install -r requirements.txt" \
    --build-cmd "make -j8"

echo ""


# =========================================================================
# 步骤 3: 注册本地构建环境
# =========================================================================
echo ">>> [3/8] 注册本地构建环境 local_pc ..."

aieffect env add-build local_pc \
    --type local \
    --work-dir "/tmp/aieffect_workdir" \
    --desc "本地 PC 构建环境" \
    --var "CC=gcc" \
    --var "CXX=g++" \
    --var "PARALLEL_JOBS=8" \
    2>/dev/null || true

echo ""


# =========================================================================
# 步骤 4: 注册 EDA 执行环境（功能仿真器）
# =========================================================================
echo ">>> [4/8] 注册 EDA 执行环境 sim_eda ..."

aieffect env add-exe sim_eda \
    --type eda \
    --desc "本地功能仿真器 (VCS/Xcelium)" \
    --timeout 7200 \
    --var "SIMULATOR=vcs" \
    --var "SIM_OPTIONS=-full64 -timescale=1ns/1ps" \
    --license "VCS_LICENSE=27000@license-server.company.com" \
    2>/dev/null || true

echo ""


# =========================================================================
# 步骤 5: 注册构建配置
# =========================================================================
echo ">>> [5/8] 注册构建配置 $BUILD_NAME ..."

aieffect build add "$BUILD_NAME" \
    --repo-name "$REPO_NAME" \
    --setup-cmd "source setup_env.sh && make deps" \
    --build-cmd "make -j8 build_all" \
    --clean-cmd "make clean" \
    --output-dir "output/sim" \
    2>/dev/null || true

echo ""


# =========================================================================
# 步骤 6: 执行 7 步编排流水线
# =========================================================================
echo ">>> [6/8] 启动 7 步编排执行 ..."
echo "    环境 → 代码仓 → 构建 → 激励 → 执行 → 收集 → 清理"
echo ""

# 构建用例参数
CASE_ARGS=""
for c in "${CASE_NAMES[@]}"; do
    CASE_ARGS="$CASE_ARGS --case $c"
done

aieffect orchestrate "$SUITE_NAME" \
    --config configs/default.yml \
    --parallel 4 \
    --build-env local_pc \
    --exe-env sim_eda \
    --repo "$REPO_NAME" \
    --build "$BUILD_NAME" \
    --snapshot "$SNAPSHOT_ID" \
    --param "VERSION=$SNAPSHOT_ID" \
    --param "BRANCH=$REPO_BRANCH_OVERRIDE" \
    $CASE_ARGS

echo ""


# =========================================================================
# 步骤 7: 导出测试报告
# =========================================================================
echo ">>> [7/8] 生成 HTML 测试报告 ..."

aieffect report results --format html

echo ""


# =========================================================================
# 步骤 8: 上传结果到远程服务器
# =========================================================================
echo ">>> [8/8] 上传结果到服务器 ($UPLOAD_TARGET) ..."

aieffect result upload \
    --type rsync \
    --rsync-target "$UPLOAD_TARGET" \
    --ssh-key "$SSH_KEY"

echo ""


# =========================================================================
# 完成
# =========================================================================
echo "============================================="
echo "  Demo A 完成"
echo "============================================="
echo ""
echo "  快照:     $SNAPSHOT_ID"
echo "  分支覆盖: $REPO_NAME -> $REPO_BRANCH_OVERRIDE"
echo "  结果:     已上传至 $UPLOAD_TARGET"
echo "  报告:     results/report.html"
echo ""
echo "  查看历史: aieffect history list --suite $SUITE_NAME"
echo "  对比结果: aieffect result compare <run_id_a> <run_id_b>"
echo "============================================="
