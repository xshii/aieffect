"""aieffect 命令行接口"""

import click

from framework import __version__


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """aieffect - AI 芯片验证效率集成平台"""


@main.command()
@click.argument("suite", default="default")
@click.option("--parallel", "-p", default=1, help="并行任务数")
@click.option("--config", "-c", default="configs/default.yml", help="配置文件路径")
def run(suite: str, parallel: int, config: str) -> None:
    """运行测试套件"""
    from framework.core.collector import save_results
    from framework.core.runner import TestRunner

    runner = TestRunner(config_path=config, parallel=parallel)
    result = runner.run_suite(suite)
    save_results(result.results)


@main.command()
@click.argument("result_dir", default="results")
@click.option("--format", "-f", "fmt", default="html", type=click.Choice(["html", "json", "junit"]))
def report(result_dir: str, fmt: str) -> None:
    """从结果目录生成测试报告"""
    from framework.core.reporter import generate_report

    generate_report(result_dir=result_dir, fmt=fmt)


@main.command()
@click.option("--registry", default="deps/manifest.yml", help="依赖包清单路径")
@click.option("--name", default=None, help="指定包名（不指定则拉取全部）")
@click.option("--version", default=None, help="指定版本（覆盖注册表默认版本）")
def fetch(registry: str, name: str | None, version: str | None) -> None:
    """拉取依赖包"""
    from framework.core.dep_manager import DepManager

    dm = DepManager(registry_path=registry)
    if name:
        dm.fetch(name, version=version)
    else:
        dm.fetch_all()


@main.command(name="deps")
@click.option("--registry", default="deps/manifest.yml", help="依赖包清单路径")
def list_deps(registry: str) -> None:
    """列出所有已注册的依赖包"""
    from framework.core.dep_manager import DepManager

    dm = DepManager(registry_path=registry)
    packages = dm.list_packages()
    if not packages:
        click.echo("没有已注册的依赖包。")
        return
    for p in packages:
        click.echo(f"  {p['name']:20s} {p['version']:12s} [{p['source']:4s}] ({p['owner']}) {p['description']}")


@main.command()
@click.argument("name")
@click.argument("version")
@click.argument("src_path")
def upload(name: str, version: str, src_path: str) -> None:
    """手动上传包到 Git LFS 存储"""
    from framework.core.dep_manager import DepManager

    dm = DepManager()
    dest = dm.upload_lfs(name, version, src_path)
    click.echo(f"已上传到: {dest}")


@main.command()
@click.option("--port", default=8888, help="监听端口")
def dashboard(port: int) -> None:
    """启动轻量级 Web 看板"""
    from framework.web.app import run_server

    run_server(port=port)


@main.command(name="apply-deps")
@click.option("--override", default=None, help="版本覆盖 YAML 文件")
@click.option("--dep-name", default=None, help="要更新的依赖名")
@click.option("--dep-version", default=None, help="新版本号")
@click.option("--show", is_flag=True, help="显示当前版本")
@click.option("--base", default="deps/manifest.yml", help="基础版本文件")
def apply_deps(override: str | None, dep_name: str | None, dep_version: str | None, show: bool, base: str) -> None:
    """应用依赖版本覆盖（供 Jenkins 流水线调用）"""
    import logging
    from pathlib import Path

    import yaml

    logger = logging.getLogger(__name__)

    def _load(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {}
        with open(p) as f:
            return yaml.safe_load(f) or {}

    if show:
        deps = _load(base).get("dependencies", {})
        if not deps:
            click.echo("未定义任何依赖。")
            return
        for name, info in sorted(deps.items()):
            ver = info.get("version", "未设置") if isinstance(info, dict) else info
            click.echo(f"  {name}: {ver}")
    elif override:
        base_data = _load(base)
        override_data = _load(override)
        if override_data:
            deps = base_data.setdefault("dependencies", {})
            for name, ver in override_data.items():
                deps.setdefault(name, {})["version"] = ver
                logger.info("  %s -> %s", name, ver)
            with open(base, "w") as f:
                yaml.dump(base_data, f, default_flow_style=False)
    elif dep_name and dep_version:
        base_data = _load(base)
        deps = base_data.setdefault("dependencies", {})
        deps.setdefault(dep_name, {})["version"] = dep_version
        logger.info("  %s -> %s", dep_name, dep_version)
        with open(base, "w") as f:
            yaml.dump(base_data, f, default_flow_style=False)
    else:
        click.echo("请指定 --override、--dep-name/--dep-version 或 --show")


if __name__ == "__main__":
    main()
