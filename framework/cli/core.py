"""核心命令：run, report, dashboard 等"""

import click

from framework.core.log_checker import LogChecker
from framework.core.reporter import generate_report
from framework.core.resource import ResourceManager
from framework.services.run_service import RunRequest, RunService


def register_commands(main: click.Group) -> None:
    """注册核心命令"""
    main.add_command(run)
    main.add_command(report)
    main.add_command(dashboard)
    main.add_command(check_log)
    main.add_command(resource_status)


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
    # 解析 key=value 参数
    params: dict[str, str] = {}
    for p in param:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip()] = v.strip()

    svc = RunService()
    svc.execute_and_persist(RunRequest(
        suite=suite, config_path=config, parallel=parallel,
        environment=env, params=params or None,
        snapshot_id=snapshot,
        case_names=list(case) if case else None,
    ))


@click.command()
@click.argument("result_dir", default="results")
@click.option("--format", "-f", "fmt", default="html", type=click.Choice(["html", "json", "junit"]))
def report(result_dir: str, fmt: str) -> None:
    """从结果目录生成测试报告"""
    generate_report(result_dir=result_dir, fmt=fmt)


@click.command()
@click.option("--port", default=8888, help="监听端口")
def dashboard(port: int) -> None:
    """启动轻量级 Web 看板"""
    from framework.web.app import run_server
    run_server(port=port)


@click.command(name="check-log")
@click.argument("log_file")
@click.option("--rules", default="configs/log_rules.yml", help="规则文件路径")
def check_log(log_file: str, rules: str) -> None:
    """对日志文件执行规则匹配检查"""
    checker = LogChecker(rules_file=rules)
    result = checker.check_file(log_file)

    status = "通过" if result.success else "失败"
    click.echo(f"日志检查 [{status}]: {result.log_source}")
    click.echo(f"规则总数: {result.total_rules}  通过: {result.passed_rules}  失败: {result.failed_rules}")

    for d in result.details:
        mark = "OK" if d.passed else "FAIL"
        click.echo(f"  [{mark:4s}] {d.rule_name} ({d.rule_type}): {d.message}")


@click.command(name="resource")
def resource_status() -> None:
    """查看资源繁忙度"""
    rm = ResourceManager()
    s = rm.status()
    click.echo(f"资源容量: {s.capacity}  使用中: {s.in_use}  可用: {s.available}")
    if s.tasks:
        click.echo("当前任务:")
        for t in s.tasks:
            click.echo(f"  - {t}")
