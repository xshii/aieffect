"""CLI — 激励管理命令"""

from __future__ import annotations

import click

from framework.cli import _parse_kv_pairs, _svc


def register(group: click.Group) -> None:
    group.add_command(stimulus_group)


@click.group(name="stimulus")
def stimulus_group() -> None:
    """激励管理"""


@stimulus_group.command(name="list")
def stimulus_list() -> None:
    """列出已注册的激励源"""
    items = _svc().stimulus.list_all()
    if not items:
        click.echo("没有已注册的激励。")
        return
    for s in items:
        source_type = s.get('source_type', '?')
        description = s.get('description', '')
        click.echo(f"  {s['name']:20s} type={source_type:10s} {description}")


@stimulus_group.command(name="add")
@click.argument("name")
@click.option(
    "--type", "source_type", default="generated",
    type=click.Choice(["repo", "generated", "stored", "external"]),
)
@click.option("--generator-cmd", default="", help="生成命令（generated 类型）")
@click.option("--storage-key", default="", help="存储 key（stored 类型）")
@click.option("--external-url", default="", help="外部 URL（external 类型）")
@click.option("--desc", default="", help="描述")
def stimulus_add(
    name: str, source_type: str, generator_cmd: str,
    storage_key: str, external_url: str, desc: str,
) -> None:
    """注册激励源"""
    spec = _svc().stimulus.create_spec({
        "name": name, "source_type": source_type,
        "generator_cmd": generator_cmd, "storage_key": storage_key,
        "external_url": external_url, "description": desc,
    })
    _svc().stimulus.register(spec)
    click.echo(f"激励已注册: {name} (type={source_type})")


@stimulus_group.command(name="remove")
@click.argument("name")
def stimulus_remove(name: str) -> None:
    """移除激励"""
    if _svc().stimulus.remove(name):
        click.echo(f"激励已移除: {name}")
    else:
        click.echo(f"激励不存在: {name}")


@stimulus_group.command(name="acquire")
@click.argument("name")
def stimulus_acquire(name: str) -> None:
    """获取激励产物"""
    art = _svc().stimulus.acquire(name)
    click.echo(f"状态: {art.status}  路径: {art.local_path}  checksum: {art.checksum}")


@stimulus_group.command(name="construct")
@click.argument("name")
@click.option("--param", multiple=True, help="构造参数 key=value（可多次）")
def stimulus_construct(name: str, param: tuple[str, ...]) -> None:
    """构造激励（模板+参数）"""
    params = _parse_kv_pairs(param)
    art = _svc().stimulus.construct(name, params=params)
    click.echo(f"状态: {art.status}  路径: {art.local_path}  checksum: {art.checksum}")


@stimulus_group.command(name="add-result-stimulus")
@click.argument("name")
@click.option("--type", "source_type", default="api", type=click.Choice(["api", "binary"]))
@click.option("--api-url", default="", help="API 地址")
@click.option("--binary-path", default="", help="二进制文件路径")
@click.option("--parser-cmd", default="", help="解析命令")
@click.option("--desc", default="", help="描述")
def stimulus_add_result(
    name: str, source_type: str, api_url: str,
    binary_path: str, parser_cmd: str, desc: str,
) -> None:
    """注册结果激励"""
    spec = _svc().stimulus.create_result_stimulus_spec({
        "name": name, "source_type": source_type,
        "api_url": api_url, "binary_path": binary_path,
        "parser_cmd": parser_cmd, "description": desc,
    })
    _svc().stimulus.register_result_stimulus(spec)
    click.echo(f"结果激励已注册: {name} (type={source_type})")


@stimulus_group.command(name="collect-result")
@click.argument("name")
def stimulus_collect_result(name: str) -> None:
    """获取结果激励"""
    art = _svc().stimulus.collect_result_stimulus(name)
    click.echo(f"状态: {art.status}  路径: {art.local_path}")
    if art.message:
        click.echo(f"信息: {art.message}")


@stimulus_group.command(name="add-trigger")
@click.argument("name")
@click.option("--type", "trigger_type", default="api", type=click.Choice(["api", "binary"]))
@click.option("--api-url", default="", help="API 地址")
@click.option("--binary-cmd", default="", help="二进制命令")
@click.option("--stimulus-name", default="", help="关联激励名称")
@click.option("--desc", default="", help="描述")
def stimulus_add_trigger(
    name: str, trigger_type: str, api_url: str,
    binary_cmd: str, stimulus_name: str, desc: str,
) -> None:
    """注册激励触发器"""
    spec = _svc().stimulus.create_trigger_spec({
        "name": name, "trigger_type": trigger_type,
        "api_url": api_url, "binary_cmd": binary_cmd,
        "stimulus_name": stimulus_name, "description": desc,
    })
    _svc().stimulus.register_trigger(spec)
    click.echo(f"触发器已注册: {name} (type={trigger_type})")


@stimulus_group.command(name="fire")
@click.argument("name")
@click.option("--stimulus-path", default="", help="激励文件路径")
def stimulus_fire(name: str, stimulus_path: str) -> None:
    """触发激励"""
    result = _svc().stimulus.trigger(name, stimulus_path=stimulus_path)
    click.echo(f"触发状态: {result.status}")
    if result.message:
        click.echo(f"信息: {result.message}")
