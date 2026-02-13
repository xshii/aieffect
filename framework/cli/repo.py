"""代码仓管理命令"""

from typing import Any

import click

from framework.core.models import RepoSpec
from framework.services.repo_service import RepoService


def register_commands(main: click.Group) -> None:
    """注册代码仓管理相关命令"""
    main.add_command(repo_group)


@click.group(name="repo")
def repo_group() -> None:
    """代码仓管理"""


@repo_group.command(name="list")
def repo_list() -> None:
    """列出已注册的代码仓"""
    svc = RepoService()
    repos = svc.list_all()
    if not repos:
        click.echo("没有已注册的代码仓。")
        return
    for r in repos:
        src = r.get("source_type", "git")
        loc = r.get("url") or r.get("tar_path") or r.get("tar_url") or r.get("api_url") or "-"
        deps = ",".join(r.get("deps", [])) or "-"
        click.echo(f"  {r['name']:20s} [{src:3s}] {loc}  deps=[{deps}]")


@repo_group.command(name="add")
@click.argument("name")
@click.option(
    "--type", "source_type", default="git",
    type=click.Choice(["git", "tar", "api"]), help="来源类型"
)
@click.option("--url", default="", help="Git 仓库地址")
@click.option("--ref", default="main", help="分支/tag/commit")
@click.option("--path", default="", help="仓内子目录")
@click.option("--tar-path", default="", help="本地 tar 包路径")
@click.option("--tar-url", default="", help="远程 tar 包 URL")
@click.option("--api-url", default="", help="API 下载地址")
@click.option("--setup-cmd", default="", help="依赖安装命令")
@click.option("--build-cmd", default="", help="编译命令")
@click.option("--dep", multiple=True, help="关联依赖包（可多次）")
def repo_add(**kwargs: Any) -> None:
    """注册代码仓（支持 git/tar/api 三种来源）"""
    svc = RepoService()
    spec = RepoSpec(
        name=kwargs["name"], source_type=kwargs.get("source_type", "git"),
        url=kwargs.get("url", ""), ref=kwargs.get("ref", "main"),
        path=kwargs.get("path", ""), tar_path=kwargs.get("tar_path", ""),
        tar_url=kwargs.get("tar_url", ""), api_url=kwargs.get("api_url", ""),
        setup_cmd=kwargs.get("setup_cmd", ""), build_cmd=kwargs.get("build_cmd", ""),
        deps=list(kwargs.get("dep", ())),
    )
    svc.register(spec)
    click.echo(f"代码仓已注册: {kwargs['name']} (type={kwargs.get('source_type', 'git')})")


@repo_group.command(name="remove")
@click.argument("name")
def repo_remove(name: str) -> None:
    """移除代码仓"""
    svc = RepoService()
    if svc.remove(name):
        click.echo(f"代码仓已移除: {name}")
    else:
        click.echo(f"代码仓不存在: {name}")


@repo_group.command(name="checkout")
@click.argument("name")
@click.option("--ref", default="", help="覆盖分支/tag")
def repo_checkout(name: str, ref: str) -> None:
    """检出代码仓到本地工作目录"""
    svc = RepoService()
    ws = svc.checkout(name, ref_override=ref)
    click.echo(f"状态: {ws.status}  路径: {ws.local_path}  commit: {ws.commit_sha}")


@repo_group.command(name="workspaces")
def repo_workspaces() -> None:
    """列出本地已检出的工作目录"""
    svc = RepoService()
    wss = svc.list_workspaces()
    if not wss:
        click.echo("没有已检出的工作目录。")
        return
    for w in wss:
        click.echo(f"  {w['repo']:20s} ref={w['ref']:15s} commit={w['commit']}  {w['path']}")


@repo_group.command(name="clean")
@click.argument("name")
def repo_clean(name: str) -> None:
    """清理代码仓本地工作目录"""
    svc = RepoService()
    count = svc.clean(name)
    click.echo(f"已清理 {count} 个工作目录")
