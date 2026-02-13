"""环境管理命令（构建环境 + 执行环境）"""

from typing import Any

import click

from framework.core.models import BuildEnvSpec, ExeEnvSpec
from framework.services.env_service import EnvService


def register_commands(main: click.Group) -> None:
    """注册环境管理相关命令"""
    main.add_command(env_group)


def _parse_kv_pairs(pairs: tuple[str, ...]) -> dict[str, str]:
    """解析 key=value 参数对"""
    result: dict[str, str] = {}
    for p in pairs:
        if "=" in p:
            k, v = p.split("=", 1)
            result[k.strip()] = v.strip()
    return result


@click.group(name="env")
def env_group() -> None:
    """执行环境管理（构建环境 + 执行环境）"""


@env_group.command(name="list")
def env_svc_list() -> None:
    """列出所有已注册的环境"""
    svc = EnvService()
    envs = svc.list_all()
    if not envs:
        click.echo("没有已注册的环境。")
        return
    for e in envs:
        cat = e.get("category", "?")
        etype = e.get("build_env_type", e.get("exe_env_type", "-"))
        click.echo(f"  {e['name']:20s} [{cat:5s}] type={etype:15s} {e.get('description', '')}")


@env_group.command(name="add-build")
@click.argument("name")
@click.option("--type", "env_type", default="local", type=click.Choice(["local", "remote"]))
@click.option("--desc", default="", help="描述")
@click.option("--work-dir", default="", help="工作目录")
@click.option("--host", default="", help="远端主机（remote 类型）")
@click.option("--port", default=22, help="SSH 端口（remote 类型）")
@click.option("--user", default="", help="SSH 用户（remote 类型）")
@click.option("--key-path", default="", help="SSH 密钥（remote 类型）")
@click.option("--var", multiple=True, help="环境变量 key=value（可多次）")
def env_add_build(**kwargs: Any) -> None:
    """注册构建环境"""
    variables = _parse_kv_pairs(kwargs.get("var", ()))
    spec = BuildEnvSpec(
        name=kwargs["name"], build_env_type=kwargs.get("env_type", "local"),
        description=kwargs.get("desc", ""), work_dir=kwargs.get("work_dir", ""),
        variables=variables, host=kwargs.get("host", ""),
        port=kwargs.get("port", 22), user=kwargs.get("user", ""),
        key_path=kwargs.get("key_path", ""),
    )
    svc = EnvService()
    svc.register_build_env(spec)
    click.echo(f"构建环境已注册: {kwargs['name']} (type={kwargs.get('env_type', 'local')})")


@env_group.command(name="add-exe")
@click.argument("name")
@click.option(
    "--type", "env_type", default="eda",
    type=click.Choice(["eda", "fpga", "silicon", "same_as_build"]),
)
@click.option("--desc", default="", help="描述")
@click.option("--api-url", default="", help="API 地址")
@click.option("--api-token", default="", help="API 令牌")
@click.option("--build-env-name", default="", help="关联构建环境（same_as_build 类型）")
@click.option("--timeout", default=3600, help="超时时间（秒）")
@click.option("--var", multiple=True, help="环境变量 key=value（可多次）")
@click.option("--license", "lics", multiple=True, help="许可证 key=value（可多次）")
def env_add_exe(**kwargs: Any) -> None:
    """注册执行环境"""
    variables = _parse_kv_pairs(kwargs.get("var", ()))
    licenses = _parse_kv_pairs(kwargs.get("lics", ()))
    spec = ExeEnvSpec(
        name=kwargs["name"], exe_env_type=kwargs.get("env_type", "eda"),
        description=kwargs.get("desc", ""), api_url=kwargs.get("api_url", ""),
        api_token=kwargs.get("api_token", ""), variables=variables,
        licenses=licenses, timeout=kwargs.get("timeout", 3600),
        build_env_name=kwargs.get("build_env_name", ""),
    )
    svc = EnvService()
    svc.register_exe_env(spec)
    click.echo(f"执行环境已注册: {kwargs['name']} (type={kwargs.get('env_type', 'eda')})")


@env_group.command(name="remove-build")
@click.argument("name")
def env_remove_build(name: str) -> None:
    """移除构建环境"""
    svc = EnvService()
    if svc.remove_build_env(name):
        click.echo(f"构建环境已移除: {name}")
    else:
        click.echo(f"构建环境不存在: {name}")


@env_group.command(name="remove-exe")
@click.argument("name")
def env_remove_exe(name: str) -> None:
    """移除执行环境"""
    svc = EnvService()
    if svc.remove_exe_env(name):
        click.echo(f"执行环境已移除: {name}")
    else:
        click.echo(f"执行环境不存在: {name}")


@env_group.command(name="apply")
@click.option("--build-env", default="", help="构建环境名称")
@click.option("--exe-env", default="", help="执行环境名称")
def env_apply(build_env: str, exe_env: str) -> None:
    """申请环境会话"""
    svc = EnvService()
    session = svc.apply(build_env_name=build_env, exe_env_name=exe_env)
    click.echo(f"会话已创建: id={session.session_id}  状态={session.status}")
    click.echo(f"工作目录: {session.work_dir}")
    click.echo(f"变量数: {len(session.resolved_vars)}")
    for k, v in sorted(session.resolved_vars.items()):
        if k != "PATH":
            click.echo(f"  {k}={v}")


@env_group.command(name="sessions")
def env_sessions() -> None:
    """列出活跃的环境会话"""
    svc = EnvService()
    sessions = svc.list_sessions()
    if not sessions:
        click.echo("没有活跃的会话。")
        return
    for s in sessions:
        click.echo(f"  {s['session_id']}  name={s['name']}  status={s['status']}")


@env_group.command(name="exec")
@click.option("--build-env", default="", help="构建环境名称")
@click.option("--exe-env", default="", help="执行环境名称")
@click.option("--cmd", required=True, help="要执行的命令")
@click.option("--timeout", default=3600, help="超时时间（秒）")
def env_svc_exec(build_env: str, exe_env: str, cmd: str, timeout: int) -> None:
    """在指定环境中执行命令"""
    svc = EnvService()
    session = svc.apply(build_env_name=build_env, exe_env_name=exe_env)
    result = svc.execute_in(session, cmd, timeout=timeout)
    svc.release(session)
    status = "成功" if result["success"] else "失败"
    click.echo(f"执行{status} (rc={result['returncode']})")
    if result["stdout"]:
        click.echo(result["stdout"])
    if result["stderr"]:
        click.echo(result["stderr"])
