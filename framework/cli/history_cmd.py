"""执行历史查询命令"""

import click

from framework.core.history import HistoryManager


def register_commands(main: click.Group) -> None:
    """注册历史查询相关命令"""
    main.add_command(history_group)


@click.group(name="history")
def history_group() -> None:
    """执行历史查询"""


@history_group.command(name="list")
@click.option("--suite", default=None, help="按套件过滤")
@click.option("--env", default=None, help="按环境过滤")
@click.option("--limit", default=20, help="最大记录数")
def history_list(suite: str | None, env: str | None, limit: int) -> None:
    """列出执行历史"""
    hm = HistoryManager()
    records = hm.query(suite=suite, environment=env, limit=limit)
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
    hm = HistoryManager()
    summary = hm.case_summary(case_name)
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
