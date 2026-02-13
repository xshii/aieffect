"""激励管理命令"""

import click

from framework.core.models import ResultStimulusSpec, StimulusSpec, TriggerSpec
from framework.services.stimulus_service import StimulusService


def register_commands(main: click.Group) -> None:
    """注册激励管理相关命令"""
    main.add_command(stimulus_group)


def _parse_kv_pairs(pairs: tuple[str, ...]) -> dict[str, str]:
    """解析 key=value 参数对"""
    result: dict[str, str] = {}
    for p in pairs:
        if "=" in p:
            k, v = p.split("=", 1)
            result[k.strip()] = v.strip()
    return result


@click.group(name="stimulus")
def stimulus_group() -> None:
    """激励管理"""


@stimulus_group.command(name="list")
def stimulus_list() -> None:
    """列出已注册的激励源"""
    svc = StimulusService()
    items = svc.list_all()
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
    spec = StimulusSpec(
        name=name, source_type=source_type,
        generator_cmd=generator_cmd, storage_key=storage_key,
        external_url=external_url, description=desc,
    )
    svc = StimulusService()
    svc.register(spec)
    click.echo(f"激励已注册: {name} (type={source_type})")


@stimulus_group.command(name="remove")
@click.argument("name")
def stimulus_remove(name: str) -> None:
    """移除激励"""
    svc = StimulusService()
    if svc.remove(name):
        click.echo(f"激励已移除: {name}")
    else:
        click.echo(f"激励不存在: {name}")


@stimulus_group.command(name="acquire")
@click.argument("name")
def stimulus_acquire(name: str) -> None:
    """获取激励产物"""
    svc = StimulusService()
    art = svc.acquire(name)
    click.echo(f"状态: {art.status}  路径: {art.local_path}  checksum: {art.checksum}")


@stimulus_group.command(name="construct")
@click.argument("name")
@click.option("--param", multiple=True, help="构造参数 key=value（可多次）")
def stimulus_construct(name: str, param: tuple[str, ...]) -> None:
    """构造激励（模板+参数）"""
    params = _parse_kv_pairs(param)
    svc = StimulusService()
    art = svc.construct(name, params=params)
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
    spec = ResultStimulusSpec(
        name=name, source_type=source_type,
        api_url=api_url, binary_path=binary_path,
        parser_cmd=parser_cmd, description=desc,
    )
    svc = StimulusService()
    svc.register_result_stimulus(spec)
    click.echo(f"结果激励已注册: {name} (type={source_type})")


@stimulus_group.command(name="collect-result")
@click.argument("name")
def stimulus_collect_result(name: str) -> None:
    """获取结果激励"""
    svc = StimulusService()
    art = svc.collect_result_stimulus(name)
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
    spec = TriggerSpec(
        name=name, trigger_type=trigger_type,
        api_url=api_url, binary_cmd=binary_cmd,
        stimulus_name=stimulus_name, description=desc,
    )
    svc = StimulusService()
    svc.register_trigger(spec)
    click.echo(f"触发器已注册: {name} (type={trigger_type})")


@stimulus_group.command(name="fire")
@click.argument("name")
@click.option("--stimulus-path", default="", help="激励文件路径")
def stimulus_fire(name: str, stimulus_path: str) -> None:
    """触发激励"""
    svc = StimulusService()
    result = svc.trigger(name, stimulus_path=stimulus_path)
    click.echo(f"触发状态: {result.status}")
    if result.message:
        click.echo(f"信息: {result.message}")
