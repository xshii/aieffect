#!/bin/bash
# =========================================================================
#  Demo B — 通过 Web 看板 API 远程执行完整流程
# =========================================================================
#
#  场景描述:
#    1. 通过 Web 看板 (REST API) 提交验证任务
#    2. 使用 EDA 功能仿真器执行
#    3. 所有依赖版本锁定到配置套 20250206B003
#    4. 将 rtl_core 仓库的分支覆盖为 br_fix_timing_closure
#    5. 编译打包后，在远程服务器 B 上执行
#    6. 分析结果 → 打包报告 → 上传到服务器 → 提供本地下载链接
#
#  前置条件:
#    先启动 Web 看板: aieffect dashboard --port 8888
#
#  使用方式:
#    chmod +x demos/demo_b_web_api.sh
#    ./demos/demo_b_web_api.sh
#
# =========================================================================

set -euo pipefail

# ----- 可配置参数 -----
API_BASE="http://localhost:8888"
SNAPSHOT_ID="20250206B003"
REPO_NAME="rtl_core"
REPO_URL="https://git.company.com/chip/rtl_core.git"
REPO_BRANCH_OVERRIDE="br_fix_timing_closure"
BUILD_NAME="rtl_build"
SUITE_NAME="smoke"
REMOTE_HOST="10.0.2.200"
REMOTE_USER="ci"
REMOTE_PORT=22
SSH_KEY="~/.ssh/id_rsa"

echo "============================================="
echo "  Demo B: Web 看板 API 远程验证流程"
echo "============================================="
echo ""
echo ">>> API 服务器: $API_BASE"
echo ">>> 远程执行:   $REMOTE_USER@$REMOTE_HOST"
echo ""


# =========================================================================
# 步骤 1: 恢复快照 — 锁定依赖版本 20250206B003
# =========================================================================
echo ">>> [1/9] 恢复依赖快照 $SNAPSHOT_ID ..."

curl -s -X POST "$API_BASE/api/snapshots/$SNAPSHOT_ID/restore" | python3 -m json.tool

echo ""


# =========================================================================
# 步骤 2: 注册代码仓（含分支覆盖）
# =========================================================================
echo ">>> [2/9] 注册代码仓 $REPO_NAME ..."

curl -s -X POST "$API_BASE/api/repos" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"$REPO_NAME\",
        \"source_type\": \"git\",
        \"url\": \"$REPO_URL\",
        \"ref\": \"main\",
        \"setup_cmd\": \"pip install -r requirements.txt\",
        \"build_cmd\": \"make -j8\"
    }" | python3 -m json.tool

echo ""


# =========================================================================
# 步骤 3: 注册远程构建环境（服务器 B）
# =========================================================================
echo ">>> [3/9] 注册远程构建环境 remote_server_b ..."

curl -s -X POST "$API_BASE/api/envs/build" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"remote_server_b\",
        \"build_env_type\": \"remote\",
        \"description\": \"远程服务器 B 构建环境\",
        \"work_dir\": \"/data/workspace/aieffect\",
        \"host\": \"$REMOTE_HOST\",
        \"port\": $REMOTE_PORT,
        \"user\": \"$REMOTE_USER\",
        \"key_path\": \"$SSH_KEY\",
        \"variables\": {
            \"CC\": \"gcc\",
            \"CXX\": \"g++\",
            \"PARALLEL_JOBS\": \"16\"
        }
    }" | python3 -m json.tool

echo ""


# =========================================================================
# 步骤 4: 注册 EDA 执行环境（功能仿真器，绑定远程构建环境）
# =========================================================================
echo ">>> [4/9] 注册 EDA 执行环境 sim_eda_remote ..."

curl -s -X POST "$API_BASE/api/envs/exe" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"sim_eda_remote\",
        \"exe_env_type\": \"eda\",
        \"description\": \"远程 EDA 功能仿真器 (VCS)\",
        \"timeout\": 7200,
        \"build_env_name\": \"remote_server_b\",
        \"variables\": {
            \"SIMULATOR\": \"vcs\",
            \"SIM_OPTIONS\": \"-full64 -timescale=1ns/1ps\"
        },
        \"licenses\": {
            \"VCS_LICENSE\": \"27000@license-server.company.com\"
        }
    }" | python3 -m json.tool

echo ""


# =========================================================================
# 步骤 5: 注册构建配置
# =========================================================================
echo ">>> [5/9] 注册构建配置 $BUILD_NAME ..."

curl -s -X POST "$API_BASE/api/builds" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"$BUILD_NAME\",
        \"repo_name\": \"$REPO_NAME\",
        \"setup_cmd\": \"source setup_env.sh && make deps\",
        \"build_cmd\": \"make -j16 build_all\",
        \"clean_cmd\": \"make clean\",
        \"output_dir\": \"output/sim\"
    }" | python3 -m json.tool

echo ""


# =========================================================================
# 步骤 6: 一键编排执行（7 步流水线）
# =========================================================================
echo ">>> [6/9] 提交编排执行计划 ..."
echo "    环境 → 代码仓 → 构建 → 激励 → 执行 → 收集 → 清理"
echo ""

# Web API 支持 repo_ref_overrides，可直接覆盖指定仓库的分支
ORCHESTRATE_RESPONSE=$(curl -s -X POST "$API_BASE/api/orchestrate" \
    -H "Content-Type: application/json" \
    -d "{
        \"suite\": \"$SUITE_NAME\",
        \"config_path\": \"configs/default.yml\",
        \"parallel\": 4,
        \"build_env_name\": \"remote_server_b\",
        \"exe_env_name\": \"sim_eda_remote\",
        \"repo_names\": [\"$REPO_NAME\"],
        \"repo_ref_overrides\": {
            \"$REPO_NAME\": \"$REPO_BRANCH_OVERRIDE\"
        },
        \"build_names\": [\"$BUILD_NAME\"],
        \"snapshot_id\": \"$SNAPSHOT_ID\",
        \"case_names\": [\"sanity_check\", \"basic_func\"],
        \"params\": {
            \"VERSION\": \"$SNAPSHOT_ID\",
            \"BRANCH\": \"$REPO_BRANCH_OVERRIDE\"
        }
    }")

echo "$ORCHESTRATE_RESPONSE" | python3 -m json.tool

# 提取 run_id 供后续使用
RUN_ID=$(echo "$ORCHESTRATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null || echo "")
echo ""
echo "    run_id: $RUN_ID"
echo ""


# =========================================================================
# 步骤 7: 导出测试报告（HTML 格式）
# =========================================================================
echo ">>> [7/9] 生成 HTML 测试报告 ..."

EXPORT_RESPONSE=$(curl -s -X POST "$API_BASE/api/results/export" \
    -H "Content-Type: application/json" \
    -d "{\"format\": \"html\"}")

echo "$EXPORT_RESPONSE" | python3 -m json.tool

REPORT_PATH=$(echo "$EXPORT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('path',''))" 2>/dev/null || echo "")
echo ""


# =========================================================================
# 步骤 8: 上传结果到服务器（API 方式）
# =========================================================================
echo ">>> [8/9] 上传结果到服务器 ..."

UPLOAD_RESPONSE=$(curl -s -X POST "$API_BASE/api/results/upload" \
    -H "Content-Type: application/json" \
    -d "{
        \"run_id\": \"$RUN_ID\",
        \"storage\": {
            \"upload_type\": \"rsync\",
            \"rsync_target\": \"$REMOTE_USER@$REMOTE_HOST:/data/results/$SUITE_NAME\",
            \"ssh_key\": \"$SSH_KEY\"
        }
    }")

echo "$UPLOAD_RESPONSE" | python3 -m json.tool

echo ""


# =========================================================================
# 步骤 9: 查询执行历史 & 提供下载链接
# =========================================================================
echo ">>> [9/9] 查询执行历史并生成下载链接 ..."

curl -s "$API_BASE/api/history?suite=$SUITE_NAME&limit=5" | python3 -m json.tool

echo ""


# =========================================================================
# 完成 — 汇总信息
# =========================================================================
echo "============================================="
echo "  Demo B 完成"
echo "============================================="
echo ""
echo "  快照:       $SNAPSHOT_ID"
echo "  分支覆盖:   $REPO_NAME -> $REPO_BRANCH_OVERRIDE"
echo "  远程执行:   $REMOTE_USER@$REMOTE_HOST"
echo "  run_id:     $RUN_ID"
echo ""
echo "  结果已上传: $REMOTE_USER@$REMOTE_HOST:/data/results/$SUITE_NAME"
echo "  HTML 报告:  $REPORT_PATH"
echo ""
echo "  ---- 本地下载链接 ----"
echo "  报告下载:   $API_BASE/api/results/export  (POST format=html)"
echo "  结果查询:   $API_BASE/api/results"
echo "  历史记录:   $API_BASE/api/history?suite=$SUITE_NAME"
echo "  结果对比:   $API_BASE/api/results/compare?run_a=$RUN_ID&run_b=<其他run_id>"
echo "============================================="
