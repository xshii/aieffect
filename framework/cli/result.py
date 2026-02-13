"""结果管理命令"""

import click

from framework.services.result_service import ResultService, StorageConfig


def register_commands(main: click.Group) -> None:
    """注册结果管理相关命令"""
    main.add_command(result_group)


@click.group(name="result")
def result_group() -> None:
    """结果管理"""


@result_group.command(name="list")
def result_list() -> None:
    """列出当前结果"""
    svc = ResultService()
    data = svc.list_results()
    s = data["summary"]
    click.echo(
        f"汇总: total={s['total']} passed={s['passed']} "
        f"failed={s['failed']} errors={s['errors']}"
    )


@result_group.command(name="compare")
@click.argument("run_a")
@click.argument("run_b")
def result_compare(run_a: str, run_b: str) -> None:
    """对比两次执行结果"""
    svc = ResultService()
    diff = svc.compare_runs(run_a, run_b)
    if "error" in diff:
        click.echo(f"错误: {diff['error']}")
        return
    click.echo(f"对比: {run_a} vs {run_b}")
    click.echo(f"总用例: {diff['total_cases']}  变化: {diff['changed_cases']}")
    for d in diff.get("diffs", []):
        click.echo(f"  {d['case']:20s} {d.get(run_a, '—')} -> {d.get(run_b, '—')}")


@result_group.command(name="clean")
def result_clean() -> None:
    """清理结果目录"""
    svc = ResultService()
    count = svc.clean_results()
    click.echo(f"已清理 {count} 个结果文件")


@result_group.command(name="upload")
@click.option(
    "--type", "upload_type", default="local",
    type=click.Choice(["local", "api", "rsync"]),
)
@click.option("--api-url", default="", help="API 上传地址")
@click.option("--api-token", default="", help="API 令牌")
@click.option("--rsync-target", default="", help="rsync 目标 user@host:/path")
@click.option("--ssh-key", default="", help="SSH 密钥路径")
def result_upload(
    upload_type: str, api_url: str, api_token: str,
    rsync_target: str, ssh_key: str,
) -> None:
    """上传结果（本地/API/rsync）"""
    cfg = StorageConfig(
        upload_type=upload_type, api_url=api_url,
        api_token=api_token, rsync_target=rsync_target,
        ssh_key=ssh_key,
    )
    svc = ResultService()
    result = svc.upload(config=cfg)
    click.echo(f"上传状态: {result['status']}")
    if result.get("message"):
        click.echo(f"信息: {result['message']}")
    if result.get("hint"):
        click.echo(f"\n{result['hint']}")
