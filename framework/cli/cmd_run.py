"""CLI — 运行命令"""

from __future__ import annotations

import click

from framework.cli import _parse_kv_pairs, _svc


def register(group: click.Group) -> None:
    group.add_command(run)


@click.command()
@click.argument("suite", default="default")
@click.option("--parallel", "-p", default=1, help="并行任务数")
@click.option("--config", "-c", default="configs/default.yml", help="配置文件路径")
@click.option("--env", "-e", default="", help="执行环境名称")
@click.option("--param", multiple=True, help="运行时参数，格式: key=value（可多次指定）")
@click.option("--snapshot", default="", help="关联构建快照 ID")
@click.option("--case", multiple=True, help="只执行指定用例（可多次指定）")
def run(
    suite: str, parallel: int, config: str, env: str,
    param: tuple[str, ...], snapshot: str, case: tuple[str, ...],
) -> None:
    """运行测试套件"""
    from framework.services.run_service import RunRequest
    params = _parse_kv_pairs(param)
    _svc().run.execute_and_persist(RunRequest(
        suite=suite, config_path=config, parallel=parallel,
        environment=env, params=params or None,
        snapshot_id=snapshot,
        case_names=list(case) if case else None,
    ))
