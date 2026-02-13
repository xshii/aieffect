"""依赖包管理命令"""

import click

from framework.core.dep_manager import DepManager
from framework.utils.yaml_io import load_yaml, save_yaml


def register_commands(main: click.Group) -> None:
    """注册依赖管理相关命令"""
    main.add_command(fetch)
    main.add_command(list_deps)
    main.add_command(resolve_dep)
    main.add_command(list_versions)
    main.add_command(upload)
    main.add_command(apply_deps)


@click.command()
@click.option("--registry", default="deps/manifest.yml", help="依赖包清单路径")
@click.option("--name", default=None, help="指定包名（不指定则拉取全部）")
@click.option("--version", default=None, help="指定版本（覆盖注册表默认版本）")
def fetch(registry: str, name: str | None, version: str | None) -> None:
    """拉取依赖包（本地优先，不存在时远程下载）"""
    dm = DepManager(registry_path=registry)
    if name:
        path = dm.fetch(name, version=version)
        click.echo(f"就绪: {name} -> {path}")
    else:
        dm.fetch_all()


@click.command(name="deps")
@click.option("--registry", default="deps/manifest.yml", help="依赖包清单路径")
def list_deps(registry: str) -> None:
    """列出所有已注册的依赖包"""
    dm = DepManager(registry_path=registry)
    packages = dm.list_packages()
    if not packages:
        click.echo("没有已注册的依赖包。")
        return
    for p in packages:
        base = p.get("base_path", "")
        base_info = f" path={base}" if base else ""
        click.echo(
            f"  {p['name']:20s} {p['version']:12s} "
            f"[{p['source']:5s}] ({p['owner']}){base_info}  {p['description']}"
        )


@click.command(name="resolve")
@click.argument("name")
@click.option("--version", default=None, help="指定版本")
@click.option("--registry", default="deps/manifest.yml", help="依赖包清单路径")
def resolve_dep(name: str, version: str | None, registry: str) -> None:
    """解析本地已安装版本路径（不下载）"""
    dm = DepManager(registry_path=registry)
    path = dm.resolve(name, version=version)
    if path:
        click.echo(str(path))
    else:
        ver = version or dm.packages[name].version
        click.echo(f"本地不存在: {name}@{ver}")
        local_versions = dm.list_local_versions(name)
        if local_versions:
            click.echo(f"已安装版本: {', '.join(local_versions)}")


@click.command(name="versions")
@click.argument("name")
@click.option("--registry", default="deps/manifest.yml", help="依赖包清单路径")
def list_versions(name: str, registry: str) -> None:
    """列出依赖包本地已安装的所有版本"""
    dm = DepManager(registry_path=registry)
    versions = dm.list_local_versions(name)
    current = dm.packages[name].version
    if not versions:
        click.echo(f"本地没有已安装版本: {name}")
        return
    for v in versions:
        marker = " <- 当前" if v == current else ""
        click.echo(f"  {v}{marker}")


@click.command()
@click.argument("name")
@click.argument("version")
@click.argument("src_path")
def upload(name: str, version: str, src_path: str) -> None:
    """手动上传包到 Git LFS 存储"""
    dm = DepManager()
    dest = dm.upload_lfs(name, version, src_path)
    click.echo(f"已上传到: {dest}")


def _show_deps(base: str) -> None:
    """显示当前依赖版本"""
    deps = load_yaml(base).get("dependencies", {})
    if not deps:
        click.echo("未定义任何依赖。")
        return
    for name, info in sorted(deps.items()):
        ver = info.get("version", "未设置") if isinstance(info, dict) else info
        click.echo(f"  {name}: {ver}")


def _apply_override_file(base: str, override: str) -> None:
    """从 YAML 文件批量覆盖依赖版本"""
    import logging
    logger = logging.getLogger(__name__)

    base_data = load_yaml(base)
    override_data = load_yaml(override)
    if not override_data:
        return

    deps = base_data.setdefault("dependencies", {})
    for name, ver in override_data.items():
        deps.setdefault(name, {})["version"] = ver
        logger.info("  %s -> %s", name, ver)
    save_yaml(base, base_data)


def _apply_single_dep(base: str, dep_name: str, dep_version: str) -> None:
    """更新单个依赖版本"""
    import logging
    logger = logging.getLogger(__name__)

    base_data = load_yaml(base)
    deps = base_data.setdefault("dependencies", {})
    deps.setdefault(dep_name, {})["version"] = dep_version
    logger.info("  %s -> %s", dep_name, dep_version)
    save_yaml(base, base_data)


@click.command(name="apply-deps")
@click.option("--override", default=None, help="版本覆盖 YAML 文件")
@click.option("--dep-name", default=None, help="要更新的依赖名")
@click.option("--dep-version", default=None, help="新版本号")
@click.option("--show", is_flag=True, help="显示当前版本")
@click.option("--base", default="deps/manifest.yml", help="基础版本文件")
def apply_deps(
    override: str | None, dep_name: str | None,
    dep_version: str | None, show: bool, base: str,
) -> None:
    """应用依赖版本覆盖（供 Jenkins 流水线调用）"""
    if show:
        _show_deps(base)
    elif override:
        _apply_override_file(base, override)
    elif dep_name and dep_version:
        _apply_single_dep(base, dep_name, dep_version)
    else:
        click.echo("请指定 --override、--dep-name/--dep-version 或 --show")
