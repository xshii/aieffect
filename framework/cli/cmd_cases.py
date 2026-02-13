"""CLI — 用例表单管理命令"""

from __future__ import annotations

from typing import Any

import click

from framework.cli import _svc


def register(group: click.Group) -> None:
    group.add_command(cases_group)


@click.group(name="cases")
def cases_group() -> None:
    """用例表单管理"""


@cases_group.command(name="list")
@click.option("--tag", default=None, help="按标签过滤")
@click.option("--env", default=None, help="按环境过滤")
def cases_list(tag: str | None, env: str | None) -> None:
    """列出已注册的用例"""
    cases = _svc().cases.list_cases(tag=tag, environment=env)
    if not cases:
        click.echo("没有已注册的用例。")
        return
    for c in cases:
        envs = ",".join(c.get("environments", [])) or "全部"
        tags = ",".join(c.get("tags", [])) or "-"
        click.echo(f"  {c['name']:20s} [{tags}] 环境={envs}  {c.get('description', '')}")


@cases_group.command(name="add")
@click.argument("name")
@click.option("--cmd", required=True, help="执行命令模板")
@click.option("--desc", default="", help="描述")
@click.option("--tag", multiple=True, help="标签（可多次指定）")
@click.option("--timeout", default=3600, help="超时时间（秒）")
@click.option("--env", multiple=True, help="绑定环境（可多次指定）")
@click.option("--repo-url", default="", help="外部仓库地址")
@click.option("--repo-ref", default="main", help="仓库分支/tag/commit")
@click.option("--repo-path", default="", help="仓内子目录")
@click.option("--repo-setup", default="", help="依赖安装命令")
@click.option("--repo-build", default="", help="编译命令")
def cases_add(**kwargs: Any) -> None:
    """添加用例"""
    repo: dict[str, str] = {}
    if kwargs.get("repo_url"):
        repo = {"url": kwargs["repo_url"], "ref": kwargs.get("repo_ref", "main")}
        for key, rkey in [("repo_path", "path"), ("repo_setup", "setup"), ("repo_build", "build")]:
            if kwargs.get(key):
                repo[rkey] = kwargs[key]

    _svc().cases.add_case(
        kwargs["name"], kwargs["cmd"], description=kwargs.get("desc", ""),
        tags=list(kwargs.get("tag", ())),
        timeout=kwargs.get("timeout", 3600),
        environments=list(kwargs.get("env", ())), repo=repo,
    )
    click.echo(f"用例已添加: {kwargs['name']}")


@cases_group.command(name="remove")
@click.argument("name")
def cases_remove(name: str) -> None:
    """删除用例"""
    if _svc().cases.remove_case(name):
        click.echo(f"用例已删除: {name}")
    else:
        click.echo(f"用例不存在: {name}")
