"""CLI — 杂项命令（快照、历史、日志检查、资源、编排、看板）"""

from __future__ import annotations

from typing import Any

import click

from framework.cli import _parse_kv_pairs, _svc


def register(group: click.Group) -> None:
    group.add_command(report)
    group.add_command(dashboard)
    group.add_command(snapshot_group)
    group.add_command(history_group)
    group.add_command(check_log)
    group.add_command(resource_status)
    group.add_command(orchestrate)


# ---- 报告 ----

@click.command()
@click.argument("result_dir", default="results")
@click.option("--format", "-f", "fmt", default="html", type=click.Choice(["html", "json", "junit"]))
def report(result_dir: str, fmt: str) -> None:
    """从结果目录生成测试报告"""
    from framework.core.reporter import generate_report
    generate_report(result_dir=result_dir, fmt=fmt)


# ---- 看板 ----

@click.command()
@click.option("--port", default=8888, help="监听端口")
def dashboard(port: int) -> None:
    """启动轻量级 Web 看板"""
    from framework.web.app import run_server
    run_server(port=port)


# ---- 快照 ----

@click.group(name="snapshot")
def snapshot_group() -> None:
    """构建版本快照管理"""


@snapshot_group.command(name="create")
@click.option("--desc", default="", help="快照描述")
@click.option("--id", "snap_id", default=None, help="自定义快照 ID")
def snapshot_create(desc: str, snap_id: str | None) -> None:
    """从当前清单创建版本快照"""
    snap = _svc().snapshots.create(description=desc, snapshot_id=snap_id)
    click.echo(f"快照已创建: {snap['id']}")


@snapshot_group.command(name="list")
def snapshot_list() -> None:
    """列出所有快照"""
    snaps = _svc().snapshots.list_snapshots()
    if not snaps:
        click.echo("没有已创建的快照。")
        return
    for s in snaps:
        click.echo(f"  {s['id']:30s} {s['created_at'][:19]}  {s.get('description', '')}")


@snapshot_group.command(name="restore")
@click.argument("snapshot_id")
def snapshot_restore(snapshot_id: str) -> None:
    """恢复指定快照到当前清单"""
    if _svc().snapshots.restore(snapshot_id):
        click.echo(f"快照已恢复: {snapshot_id}")
    else:
        click.echo(f"快照不存在: {snapshot_id}")


@snapshot_group.command(name="diff")
@click.argument("id_a")
@click.argument("id_b")
def snapshot_diff(id_a: str, id_b: str) -> None:
    """比较两个快照的差异"""
    changes = _svc().snapshots.diff(id_a, id_b)
    has_changes = False
    for section, items in changes.items():
        if items:
            has_changes = True
            click.echo(f"\n{section}:")
            for item in items:
                click.echo(f"  {item['name']:20s} {item.get(id_a, '')} -> {item.get(id_b, '')}")
    if not has_changes:
        click.echo("两个快照无差异。")


# ---- 历史 ----

@click.group(name="history")
def history_group() -> None:
    """执行历史查询"""


@history_group.command(name="list")
@click.option("--suite", default=None, help="按套件过滤")
@click.option("--env", default=None, help="按环境过滤")
@click.option("--limit", default=20, help="最大记录数")
def history_list(suite: str | None, env: str | None, limit: int) -> None:
    """列出执行历史"""
    records = _svc().history.query(suite=suite, environment=env, limit=limit)
    if not records:
        click.echo("没有执行历史。")
        return
    for r in records:
        s = r.get("summary", {})
        click.echo(
            f"  {r['run_id']}  {r['timestamp'][:19]}  suite={r['suite']:12s}  "
            f"env={r.get('environment') or '-':8s}  "
            f"通过={s.get('passed', 0)} 失败={s.get('failed', 0)} 错误={s.get('errors', 0)}"
        )


@history_group.command(name="case")
@click.argument("case_name")
def history_case(case_name: str) -> None:
    """查看单个用例的历史执行汇总"""
    summary = _svc().history.case_summary(case_name)
    click.echo(f"用例: {summary['case_name']}")
    click.echo(f"总执行次数: {summary['total_runs']}  通过: {summary['passed']}  "
               f"失败: {summary['failed']}  通过率: {summary['pass_rate']}%")
    if summary["recent"]:
        click.echo("\n最近执行:")
        for r in summary["recent"]:
            click.echo(
                f"  {r['run_id']}  {r['timestamp'][:19]}"
                f"  {r['status']:8s}  {r['duration']:.1f}s"
            )


# ---- 日志检查 ----

@click.command(name="check-log")
@click.argument("log_file")
@click.option("--rules", default="configs/log_rules.yml", help="规则文件路径")
def check_log(log_file: str, rules: str) -> None:
    """对日志文件执行规则匹配检查"""
    from framework.core.log_checker import LogChecker
    checker = LogChecker(rules_file=rules)
    result = checker.check_file(log_file)

    status = "通过" if result.success else "失败"
    click.echo(f"日志检查 [{status}]: {result.log_source}")
    click.echo(f"规则总数: {result.total_rules}  通过: {result.passed_rules}  失败: {result.failed_rules}")

    for d in result.details:
        mark = "OK" if d.passed else "FAIL"
        click.echo(f"  [{mark:4s}] {d.rule_name} ({d.rule_type}): {d.message}")


# ---- 资源 ----

@click.command(name="resource")
def resource_status() -> None:
    """查看资源繁忙度"""
    s = _svc().resources.status()
    click.echo(f"资源容量: {s.capacity}  使用中: {s.in_use}  可用: {s.available}")
    if s.tasks:
        click.echo("当前任务:")
        for t in s.tasks:
            click.echo(f"  - {t}")


# ---- 编排 ----

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
    from framework.services.execution_orchestrator import (
        ExecutionOrchestrator,
        OrchestrationPlan,
    )

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
