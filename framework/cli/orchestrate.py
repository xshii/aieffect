"""编排执行命令"""

from typing import Any

import click

from framework.services.execution_orchestrator import (
    ExecutionOrchestrator,
    OrchestrationPlan,
)


def register_commands(main: click.Group) -> None:
    """注册编排执行相关命令"""
    main.add_command(orchestrate)


def _parse_kv_pairs(pairs: tuple[str, ...]) -> dict[str, str]:
    """解析 key=value 参数对"""
    result: dict[str, str] = {}
    for p in pairs:
        if "=" in p:
            k, v = p.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _print_orchestrate_report(report: Any) -> None:
    """打印编排执行报告"""
    click.echo("\n=== 编排执行报告 ===")
    for step in report.steps:
        status = step.get("status", "?")
        detail = step.get("detail", "")
        click.echo(f"  [{status:8s}] {step['step']}" + (f"  ({detail})" if detail else ""))

    if report.suite_result:
        sr = report.suite_result
        click.echo(
            f"\n结果: total={sr.total} passed={sr.passed} "
            f"failed={sr.failed} errors={sr.errors}"
        )
    if report.run_id:
        click.echo(f"run_id: {report.run_id}")
    click.echo(f"成功: {'是' if report.success else '否'}")


@click.command(name="orchestrate")
@click.argument("suite", default="default")
@click.option("-p", "--parallel", default=1, help="并行度")
@click.option("-c", "--config", default="configs/default.yml", help="配置文件")
@click.option("--build-env", default="", help="构建环境名称")
@click.option("--exe-env", default="", help="执行环境名称")
@click.option("-e", "--env", default="", help="执行环境（兼容旧用法）")
@click.option("--repo", multiple=True, help="代码仓名称（可多次）")
@click.option("--build", "build_names", multiple=True, help="构建名称（可多次）")
@click.option("--stimulus", multiple=True, help="激励名称（可多次）")
@click.option("--snapshot", default="", help="快照 ID")
@click.option("--case", multiple=True, help="用例名称（可多次）")
@click.option("--param", multiple=True, help="参数 key=value（可多次）")
def orchestrate(**kwargs: Any) -> None:
    """7 步编排执行（环境→代码仓→构建→激励→执行→收集→清理）"""
    params = _parse_kv_pairs(kwargs.get("param", ()))
    plan = OrchestrationPlan(
        suite=kwargs.get("suite", "default"),
        config_path=kwargs.get("config", "configs/default.yml"),
        parallel=kwargs.get("parallel", 1),
        build_env_name=kwargs.get("build_env", ""),
        exe_env_name=kwargs.get("exe_env", ""),
        environment=kwargs.get("env", ""),
        repo_names=list(kwargs.get("repo", ())),
        build_names=list(kwargs.get("build_names", ())),
        stimulus_names=list(kwargs.get("stimulus", ())),
        params=params, snapshot_id=kwargs.get("snapshot", ""),
        case_names=list(kwargs.get("case", ())),
    )

    report = ExecutionOrchestrator().run(plan)
    _print_orchestrate_report(report)
