"""构建管理命令"""

import click

from framework.core.models import BuildSpec
from framework.services.build_service import BuildService


def register_commands(main: click.Group) -> None:
    """注册构建管理相关命令"""
    main.add_command(build_group)


@click.group(name="build")
def build_group() -> None:
    """构建管理"""


@build_group.command(name="list")
def build_list() -> None:
    """列出已注册的构建配置"""
    svc = BuildService()
    items = svc.list_all()
    if not items:
        click.echo("没有已注册的构建配置。")
        return
    for b in items:
        repo_name = b.get('repo_name', '-')
        build_cmd = b.get('build_cmd', '')
        click.echo(f"  {b['name']:20s} repo={repo_name:15s} build={build_cmd}")


@build_group.command(name="add")
@click.argument("name")
@click.option("--repo-name", default="", help="关联代码仓")
@click.option("--setup-cmd", default="", help="依赖安装命令")
@click.option("--build-cmd", default="", help="编译命令")
@click.option("--clean-cmd", default="", help="清理命令")
@click.option("--output-dir", default="", help="产物输出目录")
def build_add(
    name: str, repo_name: str, setup_cmd: str,
    build_cmd: str, clean_cmd: str, output_dir: str,
) -> None:
    """注册构建配置"""
    spec = BuildSpec(
        name=name, repo_name=repo_name, setup_cmd=setup_cmd,
        build_cmd=build_cmd, clean_cmd=clean_cmd, output_dir=output_dir,
    )
    svc = BuildService()
    svc.register(spec)
    click.echo(f"构建已注册: {name}")


@build_group.command(name="remove")
@click.argument("name")
def build_remove(name: str) -> None:
    """移除构建配置"""
    svc = BuildService()
    if svc.remove(name):
        click.echo(f"构建已移除: {name}")
    else:
        click.echo(f"构建配置不存在: {name}")


@build_group.command(name="run")
@click.argument("name")
@click.option("--repo-ref", default="", help="代码仓分支（新分支触发重建）")
@click.option("--force", is_flag=True, help="强制重新构建（忽略缓存）")
def build_run(name: str, repo_ref: str, force: bool) -> None:
    """执行构建（相同分支自动跳过，新分支自动重建）"""
    svc = BuildService()
    result = svc.build(name, repo_ref=repo_ref, force=force)
    if result.cached:
        click.echo(f"构建缓存命中: {name} (ref={result.repo_ref}), 跳过重复构建")
    else:
        status = "成功" if result.status == "success" else "失败"
        click.echo(f"构建{status}: {name} ({result.duration:.1f}s)")
    if result.output_path:
        click.echo(f"产物路径: {result.output_path}")
    if result.message:
        click.echo(f"信息: {result.message}")
