#!/usr/bin/env python3
"""Demo A — 本地 PC 命令行完整验证流程

场景:
  1. 恢复快照 20250206B003，锁定所有依赖版本
  2. 注册 rtl_core 代码仓，将分支覆盖为 br_fix_timing_closure
  3. 在本地 PC 上使用 EDA 功能仿真器编译并执行选定用例
  4. 分析结果并上传日志到远程服务器保存

使用方式:
  python demos/demo_a_local_cli.py
"""

from framework.core.models import (
    BuildEnvSpec,
    BuildSpec,
    ExeEnvSpec,
    RepoSpec,
)
from framework.core.reporter import generate_report
from framework.core.snapshot import SnapshotManager
from framework.services.build_service import BuildService
from framework.services.env_service import EnvService
from framework.services.execution_orchestrator import (
    ExecutionOrchestrator,
    OrchestrationPlan,
)
from framework.services.repo_service import RepoService
from framework.services.result_service import ResultService, StorageConfig

# =========================================================================
# 配置参数 — 根据实际项目修改此处
# =========================================================================

SNAPSHOT_ID = "20250206B003"           # 依赖配置套版本

REPO_NAME = "rtl_core"                # 代码仓名称
REPO_URL = "https://git.company.com/chip/rtl_core.git"
REPO_BRANCH = "br_fix_timing_closure" # 要验证的分支

BUILD_NAME = "rtl_build"              # 构建配置名称
SUITE_NAME = "smoke"                  # 测试套名称
CASE_NAMES = ["sanity_check", "basic_func"]  # 选定用例

UPLOAD_TARGET = "ci@10.0.1.100:/data/results"  # 日志上传目标
SSH_KEY = "~/.ssh/id_rsa"


def main():
    print("=" * 50)
    print("  Demo A: 本地 PC CLI 完整验证流程")
    print("=" * 50)

    # -----------------------------------------------------------------
    # 步骤 1: 恢复快照，锁定所有依赖版本为 20250206B003
    # -----------------------------------------------------------------
    print(f"\n[1/8] 恢复依赖快照 {SNAPSHOT_ID} ...")

    sm = SnapshotManager()
    sm.restore(SNAPSHOT_ID)
    print(f"  快照已恢复，所有依赖版本已锁定到 {SNAPSHOT_ID}")

    # -----------------------------------------------------------------
    # 步骤 2: 注册代码仓，分支指向 br_fix_timing_closure
    # -----------------------------------------------------------------
    print(f"\n[2/8] 注册代码仓 {REPO_NAME} (分支: {REPO_BRANCH}) ...")

    repo_svc = RepoService()
    repo_svc.remove(REPO_NAME)  # 清除旧注册
    repo_svc.register(RepoSpec(
        name=REPO_NAME,
        source_type="git",
        url=REPO_URL,
        ref=REPO_BRANCH,
        setup_cmd="pip install -r requirements.txt",
        build_cmd="make -j8",
    ))
    print(f"  代码仓已注册: {REPO_NAME} -> {REPO_BRANCH}")

    # -----------------------------------------------------------------
    # 步骤 3: 注册本地构建环境
    # -----------------------------------------------------------------
    print("\n[3/8] 注册本地构建环境 local_pc ...")

    env_svc = EnvService()
    env_svc.register_build_env(BuildEnvSpec(
        name="local_pc",
        build_env_type="local",
        description="本地 PC 构建环境",
        work_dir="/tmp/aieffect_workdir",
        variables={"CC": "gcc", "CXX": "g++", "PARALLEL_JOBS": "8"},
    ))

    # -----------------------------------------------------------------
    # 步骤 4: 注册 EDA 功能仿真器执行环境
    # -----------------------------------------------------------------
    print("\n[4/8] 注册 EDA 执行环境 sim_eda ...")

    env_svc.register_exe_env(ExeEnvSpec(
        name="sim_eda",
        exe_env_type="eda",
        description="本地功能仿真器 (VCS/Xcelium)",
        timeout=7200,
        variables={"SIMULATOR": "vcs", "SIM_OPTIONS": "-full64 -timescale=1ns/1ps"},
        licenses={"VCS_LICENSE": "27000@license-server.company.com"},
    ))

    # -----------------------------------------------------------------
    # 步骤 5: 注册构建配置
    # -----------------------------------------------------------------
    print(f"\n[5/8] 注册构建配置 {BUILD_NAME} ...")

    build_svc = BuildService()
    build_svc.register(BuildSpec(
        name=BUILD_NAME,
        repo_name=REPO_NAME,
        setup_cmd="source setup_env.sh && make deps",
        build_cmd="make -j8 build_all",
        clean_cmd="make clean",
        output_dir="output/sim",
    ))

    # -----------------------------------------------------------------
    # 步骤 6: 7 步编排执行
    #   环境 → 代码仓 → 构建 → 激励 → 执行 → 收集 → 清理
    # -----------------------------------------------------------------
    print(f"\n[6/8] 启动 7 步编排执行 (套件={SUITE_NAME}) ...")
    print("  环境 -> 代码仓 -> 构建 -> 激励 -> 执行 -> 收集 -> 清理")

    plan = OrchestrationPlan(
        suite=SUITE_NAME,
        config_path="configs/default.yml",
        parallel=4,
        build_env_name="local_pc",
        exe_env_name="sim_eda",
        repo_names=[REPO_NAME],
        repo_ref_overrides={REPO_NAME: REPO_BRANCH},
        build_names=[BUILD_NAME],
        snapshot_id=SNAPSHOT_ID,
        case_names=CASE_NAMES,
        params={"VERSION": SNAPSHOT_ID, "BRANCH": REPO_BRANCH},
    )

    report = ExecutionOrchestrator().run(plan)

    # 打印各步骤状态
    for step in report.steps:
        status = step.get("status", "?")
        detail = step.get("detail", "")
        print(f"  [{status:8s}] {step['step']}" + (f"  ({detail})" if detail else ""))

    if report.suite_result:
        sr = report.suite_result
        print(f"\n  结果: total={sr.total} passed={sr.passed} "
              f"failed={sr.failed} errors={sr.errors}")
    print(f"  run_id: {report.run_id}")
    print(f"  成功: {'是' if report.success else '否'}")

    # -----------------------------------------------------------------
    # 步骤 7: 生成 HTML 测试报告
    # -----------------------------------------------------------------
    print("\n[7/8] 生成 HTML 测试报告 ...")

    generate_report(result_dir="results", fmt="html")

    # -----------------------------------------------------------------
    # 步骤 8: 上传结果到远程服务器
    # -----------------------------------------------------------------
    print(f"\n[8/8] 上传结果到服务器 ({UPLOAD_TARGET}) ...")

    result_svc = ResultService()
    upload_result = result_svc.upload(config=StorageConfig(
        upload_type="rsync",
        rsync_target=UPLOAD_TARGET,
        ssh_key=SSH_KEY,
    ))
    print(f"  上传状态: {upload_result['status']}")

    # -----------------------------------------------------------------
    # 完成
    # -----------------------------------------------------------------
    print("\n" + "=" * 50)
    print("  Demo A 完成")
    print("=" * 50)
    print(f"  快照:       {SNAPSHOT_ID}")
    print(f"  分支覆盖:   {REPO_NAME} -> {REPO_BRANCH}")
    print(f"  结果上传:   {UPLOAD_TARGET}")
    print(f"  HTML 报告:  results/report.html")
    print()
    print(f"  查看历史:   aieffect history list --suite {SUITE_NAME}")
    print(f"  对比结果:   aieffect result compare <run_id_a> <run_id_b>")


if __name__ == "__main__":
    main()
