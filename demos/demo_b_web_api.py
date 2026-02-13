#!/usr/bin/env python3
"""Demo B — 通过 Web 看板远程执行完整验证流程

场景:
  1. 通过网页看板 (REST API) 提交验证任务
  2. 恢复快照 20250206B003，锁定所有依赖版本
  3. 将 rtl_core 仓库的分支覆盖为 br_fix_timing_closure
  4. 在远程服务器 B 上编译并使用 EDA 功能仿真器执行
  5. 分析结果 → 打包报告 → 上传到服务器 → 提供本地下载链接

前置条件:
  启动 Web 看板:  aieffect dashboard --port 8888

使用方式:
  python demos/demo_b_web_api.py

==========================================================================
网页操作指导 (手动操作时参考):

  1. 打开浏览器，访问 http://localhost:8888
  2. 进入「快照管理」，点击「恢复」→ 选择 20250206B003
  3. 进入「代码仓」→「添加」，填写仓库信息 (git, url, ref)
  4. 进入「环境」→「添加构建环境」，选择 remote 类型，填写服务器 B 信息
  5. 进入「环境」→「添加执行环境」，选择 eda 类型
  6. 进入「构建」→「添加」，关联代码仓和构建命令
  7. 进入「编排执行」，填写完整计划后点击「执行」
  8. 执行完成后，在「结果」页面点击「导出报告」→ 选择 HTML
  9. 点击「上传结果」，选择 rsync 方式，填写目标服务器
  10. 在「结果」页面获取下载链接

  对应的 REST API 接口:
    快照恢复:     POST /api/snapshots/{id}/restore
    注册代码仓:   POST /api/repos
    注册构建环境:  POST /api/envs/build
    注册执行环境:  POST /api/envs/exe
    注册构建配置:  POST /api/builds
    编排执行:     POST /api/orchestrate
    导出报告:     POST /api/results/export
    上传结果:     POST /api/results/upload
    查看历史:     GET  /api/history
    结果对比:     GET  /api/results/compare?run_a=X&run_b=Y
==========================================================================
"""

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

# =========================================================================
# 配置参数 — 根据实际项目修改此处
# =========================================================================

API_BASE = "http://localhost:8888"     # Web 看板地址

SNAPSHOT_ID = "20250206B003"           # 依赖配置套版本

REPO_NAME = "rtl_core"                # 代码仓名称
REPO_URL = "https://git.company.com/chip/rtl_core.git"
REPO_BRANCH = "br_fix_timing_closure" # 要验证的分支

BUILD_NAME = "rtl_build"              # 构建配置名称
SUITE_NAME = "smoke"                  # 测试套名称
CASE_NAMES = ["sanity_check", "basic_func"]  # 选定用例

# 远程服务器 B 信息
REMOTE_HOST = "10.0.2.200"
REMOTE_USER = "ci"
REMOTE_PORT = 22
SSH_KEY = "~/.ssh/id_rsa"


# =========================================================================
# HTTP 工具
# =========================================================================


def api_get(path: str) -> dict:
    """发送 GET 请求到 Web 看板"""
    url = f"{API_BASE}{path}"
    req = Request(url)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_post(path: str, data: dict | None = None) -> dict:
    """发送 POST 请求到 Web 看板"""
    url = f"{API_BASE}{path}"
    body = json.dumps(data or {}).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def print_json(data: dict) -> None:
    """格式化打印 JSON 响应"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


# =========================================================================
# 主流程
# =========================================================================


def main():
    print("=" * 55)
    print("  Demo B: Web 看板 API 远程验证流程")
    print("=" * 55)
    print(f"  API 服务器: {API_BASE}")
    print(f"  远程执行:   {REMOTE_USER}@{REMOTE_HOST}")

    # 检查看板服务是否启动
    try:
        api_get("/api/resource")
    except (URLError, ConnectionError, OSError):
        print("\n  [错误] 无法连接到 Web 看板，请先启动:")
        print(f"    aieffect dashboard --port 8888")
        return

    # -----------------------------------------------------------------
    # 步骤 1: 恢复快照，锁定所有依赖版本
    #
    # 网页操作: 快照管理 → 选择 20250206B003 → 点击「恢复」
    # -----------------------------------------------------------------
    print(f"\n[1/9] 恢复依赖快照 {SNAPSHOT_ID} ...")

    resp = api_post(f"/api/snapshots/{SNAPSHOT_ID}/restore")
    print(f"  {resp.get('message', resp)}")

    # -----------------------------------------------------------------
    # 步骤 2: 注册代码仓
    #
    # 网页操作: 代码仓 → 添加 → 填写:
    #   名称:     rtl_core
    #   类型:     git
    #   URL:      https://git.company.com/chip/rtl_core.git
    #   分支:     main (默认，后续在编排时覆盖)
    #   安装命令: pip install -r requirements.txt
    #   编译命令: make -j8
    # -----------------------------------------------------------------
    print(f"\n[2/9] 注册代码仓 {REPO_NAME} ...")

    resp = api_post("/api/repos", {
        "name": REPO_NAME,
        "source_type": "git",
        "url": REPO_URL,
        "ref": "main",
        "setup_cmd": "pip install -r requirements.txt",
        "build_cmd": "make -j8",
    })
    print(f"  {resp.get('message', resp)}")

    # -----------------------------------------------------------------
    # 步骤 3: 注册远程构建环境 (服务器 B)
    #
    # 网页操作: 环境 → 添加构建环境 → 填写:
    #   名称:   remote_server_b
    #   类型:   remote
    #   主机:   10.0.2.200
    #   端口:   22
    #   用户:   ci
    #   密钥:   ~/.ssh/id_rsa
    #   工作目录: /data/workspace/aieffect
    #   变量:   CC=gcc, CXX=g++, PARALLEL_JOBS=16
    # -----------------------------------------------------------------
    print("\n[3/9] 注册远程构建环境 remote_server_b ...")

    resp = api_post("/api/envs/build", {
        "name": "remote_server_b",
        "build_env_type": "remote",
        "description": "远程服务器 B 构建环境",
        "work_dir": "/data/workspace/aieffect",
        "host": REMOTE_HOST,
        "port": REMOTE_PORT,
        "user": REMOTE_USER,
        "key_path": SSH_KEY,
        "variables": {"CC": "gcc", "CXX": "g++", "PARALLEL_JOBS": "16"},
    })
    print(f"  {resp.get('message', resp)}")

    # -----------------------------------------------------------------
    # 步骤 4: 注册 EDA 执行环境 (功能仿真器)
    #
    # 网页操作: 环境 → 添加执行环境 → 填写:
    #   名称:       sim_eda_remote
    #   类型:       eda
    #   超时:       7200 秒
    #   关联构建:   remote_server_b
    #   变量:       SIMULATOR=vcs, SIM_OPTIONS=-full64 -timescale=1ns/1ps
    #   许可证:     VCS_LICENSE=27000@license-server.company.com
    # -----------------------------------------------------------------
    print("\n[4/9] 注册 EDA 执行环境 sim_eda_remote ...")

    resp = api_post("/api/envs/exe", {
        "name": "sim_eda_remote",
        "exe_env_type": "eda",
        "description": "远程 EDA 功能仿真器 (VCS)",
        "timeout": 7200,
        "build_env_name": "remote_server_b",
        "variables": {
            "SIMULATOR": "vcs",
            "SIM_OPTIONS": "-full64 -timescale=1ns/1ps",
        },
        "licenses": {"VCS_LICENSE": "27000@license-server.company.com"},
    })
    print(f"  {resp.get('message', resp)}")

    # -----------------------------------------------------------------
    # 步骤 5: 注册构建配置
    #
    # 网页操作: 构建 → 添加 → 填写:
    #   名称:       rtl_build
    #   关联代码仓: rtl_core
    #   安装命令:   source setup_env.sh && make deps
    #   编译命令:   make -j16 build_all
    #   清理命令:   make clean
    #   产物目录:   output/sim
    # -----------------------------------------------------------------
    print(f"\n[5/9] 注册构建配置 {BUILD_NAME} ...")

    resp = api_post("/api/builds", {
        "name": BUILD_NAME,
        "repo_name": REPO_NAME,
        "setup_cmd": "source setup_env.sh && make deps",
        "build_cmd": "make -j16 build_all",
        "clean_cmd": "make clean",
        "output_dir": "output/sim",
    })
    print(f"  {resp.get('message', resp)}")

    # -----------------------------------------------------------------
    # 步骤 6: 一键编排执行 (7 步流水线)
    #
    # 网页操作: 编排执行 → 填写完整计划:
    #   测试套:     smoke
    #   并行度:     4
    #   构建环境:   remote_server_b
    #   执行环境:   sim_eda_remote
    #   代码仓:     [rtl_core]
    #   分支覆盖:   {rtl_core: br_fix_timing_closure}  ← 关键！
    #   构建名称:   [rtl_build]
    #   快照 ID:    20250206B003
    #   选定用例:   [sanity_check, basic_func]
    #   → 点击「执行」
    # -----------------------------------------------------------------
    print(f"\n[6/9] 提交编排执行计划 ...")
    print("  环境 -> 代码仓 -> 构建 -> 激励 -> 执行 -> 收集 -> 清理")

    resp = api_post("/api/orchestrate", {
        "suite": SUITE_NAME,
        "config_path": "configs/default.yml",
        "parallel": 4,
        "build_env_name": "remote_server_b",
        "exe_env_name": "sim_eda_remote",
        "repo_names": [REPO_NAME],
        "repo_ref_overrides": {
            REPO_NAME: REPO_BRANCH,       # 覆盖 rtl_core 的分支
        },
        "build_names": [BUILD_NAME],
        "snapshot_id": SNAPSHOT_ID,
        "case_names": CASE_NAMES,
        "params": {"VERSION": SNAPSHOT_ID, "BRANCH": REPO_BRANCH},
    })

    run_id = resp.get("run_id", "")
    success = resp.get("success", False)

    # 打印各步骤状态
    for step in resp.get("steps", []):
        status = step.get("status", "?")
        print(f"  [{status:8s}] {step.get('step', '?')}")

    sr = resp.get("suite_result")
    if sr:
        print(f"\n  结果: total={sr['total']} passed={sr['passed']} "
              f"failed={sr['failed']} errors={sr['errors']}")
    print(f"  run_id:  {run_id}")
    print(f"  成功:    {'是' if success else '否'}")

    # -----------------------------------------------------------------
    # 步骤 7: 导出 HTML 测试报告
    #
    # 网页操作: 结果 → 导出报告 → 格式选择 HTML → 下载
    # -----------------------------------------------------------------
    print("\n[7/9] 生成 HTML 测试报告 ...")

    resp = api_post("/api/results/export", {"format": "html"})
    report_path = resp.get("path", "")
    print(f"  报告路径: {report_path}")

    # -----------------------------------------------------------------
    # 步骤 8: 上传结果到服务器 B
    #
    # 网页操作: 结果 → 上传 → 方式选择 rsync → 填写:
    #   目标:   ci@10.0.2.200:/data/results/smoke
    #   密钥:   ~/.ssh/id_rsa
    # -----------------------------------------------------------------
    print(f"\n[8/9] 上传结果到服务器 B ...")

    rsync_target = f"{REMOTE_USER}@{REMOTE_HOST}:/data/results/{SUITE_NAME}"
    resp = api_post("/api/results/upload", {
        "run_id": run_id,
        "storage": {
            "upload_type": "rsync",
            "rsync_target": rsync_target,
            "ssh_key": SSH_KEY,
        },
    })
    print(f"  上传状态: {resp.get('status', resp)}")

    # -----------------------------------------------------------------
    # 步骤 9: 查看历史 & 提供下载链接
    #
    # 网页操作: 历史 → 选择最近一次执行 → 查看详情/下载
    # -----------------------------------------------------------------
    print(f"\n[9/9] 查询执行历史 ...")

    resp = api_get(f"/api/history?suite={SUITE_NAME}&limit=3")
    records = resp.get("records", [])
    for r in records:
        s = r.get("summary", {})
        print(f"  {r['run_id']}  {r['timestamp'][:19]}  "
              f"passed={s.get('passed', 0)} failed={s.get('failed', 0)}")

    # -----------------------------------------------------------------
    # 完成 — 汇总信息与下载链接
    # -----------------------------------------------------------------
    print("\n" + "=" * 55)
    print("  Demo B 完成")
    print("=" * 55)
    print(f"  快照:       {SNAPSHOT_ID}")
    print(f"  分支覆盖:   {REPO_NAME} -> {REPO_BRANCH}")
    print(f"  远程执行:   {REMOTE_USER}@{REMOTE_HOST}")
    print(f"  run_id:     {run_id}")
    print()
    print(f"  结果已上传: {rsync_target}")
    print(f"  HTML 报告:  {report_path}")
    print()
    print("  ---- 本地访问 / 下载链接 ----")
    print(f"  看板首页:   {API_BASE}/")
    print(f"  结果列表:   {API_BASE}/api/results")
    print(f"  报告导出:   {API_BASE}/api/results/export  (POST format=html)")
    print(f"  执行历史:   {API_BASE}/api/history?suite={SUITE_NAME}")
    if run_id:
        print(f"  结果对比:   {API_BASE}/api/results/compare"
              f"?run_a={run_id}&run_b=<other_run_id>")


if __name__ == "__main__":
    main()
