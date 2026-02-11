"""aieffect 命令行接口"""

import click

from framework import __version__
from framework.core.case_manager import CaseManager
from framework.core.dep_manager import DepManager
from framework.core.history import HistoryManager
from framework.core.log_checker import LogChecker
from framework.core.reporter import generate_report
from framework.core.resource import ResourceManager
from framework.core.snapshot import SnapshotManager
from framework.services.run_service import RunRequest, RunService
from framework.utils.yaml_io import load_yaml, save_yaml


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """aieffect - AI 芯片验证效率集成平台"""


# =========================================================================
# 原有命令
# =========================================================================


@main.command()
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
    svc.execute(RunRequest(
        suite=suite, config_path=config, parallel=parallel,
        environment=env, params=params or None,
        snapshot_id=snapshot,
        case_names=list(case) if case else None,
    ))


@main.command()
@click.argument("result_dir", default="results")
@click.option("--format", "-f", "fmt", default="html", type=click.Choice(["html", "json", "junit"]))
def report(result_dir: str, fmt: str) -> None:
    """从结果目录生成测试报告"""
    generate_report(result_dir=result_dir, fmt=fmt)


@main.command()
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


@main.command(name="deps")
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


@main.command(name="resolve")
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


@main.command(name="versions")
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


@main.command()
@click.argument("name")
@click.argument("version")
@click.argument("src_path")
def upload(name: str, version: str, src_path: str) -> None:
    """手动上传包到 Git LFS 存储"""
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
def apply_deps(
    override: str | None, dep_name: str | None,
    dep_version: str | None, show: bool, base: str,
) -> None:
    """应用依赖版本覆盖（供 Jenkins 流水线调用）"""
    import logging
    logger = logging.getLogger(__name__)

    if show:
        deps = load_yaml(base).get("dependencies", {})
        if not deps:
            click.echo("未定义任何依赖。")
            return
        for name, info in sorted(deps.items()):
            ver = info.get("version", "未设置") if isinstance(info, dict) else info
            click.echo(f"  {name}: {ver}")
    elif override:
        base_data = load_yaml(base)
        override_data = load_yaml(override)
        if override_data:
            deps = base_data.setdefault("dependencies", {})
            for name, ver in override_data.items():
                deps.setdefault(name, {})["version"] = ver
                logger.info("  %s -> %s", name, ver)
            save_yaml(base, base_data)
    elif dep_name and dep_version:
        base_data = load_yaml(base)
        deps = base_data.setdefault("dependencies", {})
        deps.setdefault(dep_name, {})["version"] = dep_version
        logger.info("  %s -> %s", dep_name, dep_version)
        save_yaml(base, base_data)
    else:
        click.echo("请指定 --override、--dep-name/--dep-version 或 --show")


# =========================================================================
# 用例表单管理
# =========================================================================


@main.group(name="cases")
def cases_group() -> None:
    """用例表单管理"""


@cases_group.command(name="list")
@click.option("--tag", default=None, help="按标签过滤")
@click.option("--env", default=None, help="按环境过滤")
def cases_list(tag: str | None, env: str | None) -> None:
    """列出已注册的用例"""
    cm = CaseManager()
    cases = cm.list_cases(tag=tag, environment=env)
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
def cases_add(
    name: str, cmd: str, desc: str, tag: tuple[str, ...], timeout: int,
    env: tuple[str, ...], repo_url: str, repo_ref: str, repo_path: str,
    repo_setup: str, repo_build: str,
) -> None:
    """添加用例"""
    from framework.core.case_manager import CaseManager

    repo: dict[str, str] = {}
    if repo_url:
        repo = {"url": repo_url, "ref": repo_ref}
        if repo_path:
            repo["path"] = repo_path
        if repo_setup:
            repo["setup"] = repo_setup
        if repo_build:
            repo["build"] = repo_build

    cm = CaseManager()
    cm.add_case(
        name, cmd, description=desc, tags=list(tag),
        timeout=timeout, environments=list(env), repo=repo,
    )
    click.echo(f"用例已添加: {name}")


@cases_group.command(name="remove")
@click.argument("name")
def cases_remove(name: str) -> None:
    """删除用例"""
    cm = CaseManager()
    if cm.remove_case(name):
        click.echo(f"用例已删除: {name}")
    else:
        click.echo(f"用例不存在: {name}")


# =========================================================================
# 环境管理
# =========================================================================


@cases_group.command(name="env-add")
@click.argument("name")
@click.option("--desc", default="", help="描述")
def env_add(name: str, desc: str) -> None:
    """添加执行环境"""
    cm = CaseManager()
    cm.add_environment(name, description=desc)
    click.echo(f"环境已添加: {name}")


@cases_group.command(name="env-list")
def env_list() -> None:
    """列出所有环境"""
    cm = CaseManager()
    envs = cm.list_environments()
    if not envs:
        click.echo("没有已注册的环境。")
        return
    for e in envs:
        click.echo(f"  {e['name']:20s} {e.get('description', '')}")


# =========================================================================
# 构建版本快照
# =========================================================================


@main.group(name="snapshot")
def snapshot_group() -> None:
    """构建版本快照管理"""


@snapshot_group.command(name="create")
@click.option("--desc", default="", help="快照描述")
@click.option("--id", "snap_id", default=None, help="自定义快照 ID")
def snapshot_create(desc: str, snap_id: str | None) -> None:
    """从当前清单创建版本快照"""
    sm = SnapshotManager()
    snap = sm.create(description=desc, snapshot_id=snap_id)
    click.echo(f"快照已创建: {snap['id']}")


@snapshot_group.command(name="list")
def snapshot_list() -> None:
    """列出所有快照"""
    sm = SnapshotManager()
    snaps = sm.list_snapshots()
    if not snaps:
        click.echo("没有已创建的快照。")
        return
    for s in snaps:
        click.echo(f"  {s['id']:30s} {s['created_at'][:19]}  {s.get('description', '')}")


@snapshot_group.command(name="restore")
@click.argument("snapshot_id")
def snapshot_restore(snapshot_id: str) -> None:
    """恢复指定快照到当前清单"""
    sm = SnapshotManager()
    if sm.restore(snapshot_id):
        click.echo(f"快照已恢复: {snapshot_id}")
    else:
        click.echo(f"快照不存在: {snapshot_id}")


@snapshot_group.command(name="diff")
@click.argument("id_a")
@click.argument("id_b")
def snapshot_diff(id_a: str, id_b: str) -> None:
    """比较两个快照的差异"""
    sm = SnapshotManager()
    changes = sm.diff(id_a, id_b)
    has_changes = False
    for section, items in changes.items():
        if items:
            has_changes = True
            click.echo(f"\n{section}:")
            for item in items:
                click.echo(f"  {item['name']:20s} {item.get(id_a, '')} -> {item.get(id_b, '')}")
    if not has_changes:
        click.echo("两个快照无差异。")


# =========================================================================
# 执行历史
# =========================================================================


@main.group(name="history")
def history_group() -> None:
    """执行历史查询"""


@history_group.command(name="list")
@click.option("--suite", default=None, help="按套件过滤")
@click.option("--env", default=None, help="按环境过滤")
@click.option("--limit", default=20, help="最大记录数")
def history_list(suite: str | None, env: str | None, limit: int) -> None:
    """列出执行历史"""
    hm = HistoryManager()
    records = hm.query(suite=suite, environment=env, limit=limit)
    if not records:
        click.echo("没有执行历史。")
        return
    for r in records:
        s = r.get("summary", {})
        click.echo(
            f"  {r['run_id']}  {r['timestamp'][:19]}  suite={r['suite']:12s}  "
            f"env={r.get('environment') or '-':8s}  "
            f"通过={s.get('passed', 0)} 失败={s.get('failed', 0)} 错误={s.get('errors', 0)}"
        )


@history_group.command(name="case")
@click.argument("case_name")
def history_case(case_name: str) -> None:
    """查看单个用例的历史执行汇总"""
    hm = HistoryManager()
    summary = hm.case_summary(case_name)
    click.echo(f"用例: {summary['case_name']}")
    click.echo(f"总执行次数: {summary['total_runs']}  通过: {summary['passed']}  "
               f"失败: {summary['failed']}  通过率: {summary['pass_rate']}%")
    if summary["recent"]:
        click.echo("\n最近执行:")
        for r in summary["recent"]:
            click.echo(
                f"  {r['run_id']}  {r['timestamp'][:19]}"
                f"  {r['status']:8s}  {r['duration']:.1f}s"
            )


# =========================================================================
# 日志检查
# =========================================================================


@main.command(name="check-log")
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


# =========================================================================
# 资源管理
# =========================================================================


@main.command(name="resource")
def resource_status() -> None:
    """查看资源繁忙度"""
    rm = ResourceManager()
    s = rm.status()
    click.echo(f"资源容量: {s.capacity}  使用中: {s.in_use}  可用: {s.available}")
    if s.tasks:
        click.echo("当前任务:")
        for t in s.tasks:
            click.echo(f"  - {t}")


# =========================================================================
# 代码仓管理
# =========================================================================


@main.group(name="repo")
def repo_group() -> None:
    """代码仓管理"""


@repo_group.command(name="list")
def repo_list() -> None:
    """列出已注册的代码仓"""
    from framework.services.repo_service import RepoService
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
@click.option("--type", "source_type", default="git", type=click.Choice(["git", "tar", "api"]), help="来源类型")
@click.option("--url", default="", help="Git 仓库地址")
@click.option("--ref", default="main", help="分支/tag/commit")
@click.option("--path", default="", help="仓内子目录")
@click.option("--tar-path", default="", help="本地 tar 包路径")
@click.option("--tar-url", default="", help="远程 tar 包 URL")
@click.option("--api-url", default="", help="API 下载地址")
@click.option("--setup-cmd", default="", help="依赖安装命令")
@click.option("--build-cmd", default="", help="编译命令")
@click.option("--dep", multiple=True, help="关联依赖包（可多次）")
def repo_add(
    name: str, source_type: str, url: str, ref: str, path: str,
    tar_path: str, tar_url: str, api_url: str,
    setup_cmd: str, build_cmd: str, dep: tuple[str, ...],
) -> None:
    """注册代码仓（支持 git/tar/api 三种来源）"""
    from framework.core.models import RepoSpec
    from framework.services.repo_service import RepoService
    svc = RepoService()
    spec = RepoSpec(
        name=name, source_type=source_type, url=url, ref=ref, path=path,
        tar_path=tar_path, tar_url=tar_url, api_url=api_url,
        setup_cmd=setup_cmd, build_cmd=build_cmd, deps=list(dep),
    )
    svc.register(spec)
    click.echo(f"代码仓已注册: {name} (type={source_type})")


@repo_group.command(name="remove")
@click.argument("name")
def repo_remove(name: str) -> None:
    """移除代码仓"""
    from framework.services.repo_service import RepoService
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
    from framework.services.repo_service import RepoService
    svc = RepoService()
    ws = svc.checkout(name, ref_override=ref)
    click.echo(f"状态: {ws.status}  路径: {ws.local_path}  commit: {ws.commit_sha}")


@repo_group.command(name="workspaces")
def repo_workspaces() -> None:
    """列出本地已检出的工作目录"""
    from framework.services.repo_service import RepoService
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
    from framework.services.repo_service import RepoService
    svc = RepoService()
    count = svc.clean(name)
    click.echo(f"已清理 {count} 个工作目录")


# =========================================================================
# 环境管理（独立服务）
# =========================================================================


@main.group(name="env")
def env_group() -> None:
    """执行环境管理"""


@env_group.command(name="list")
def env_svc_list() -> None:
    """列出已注册的执行环境"""
    from framework.services.env_service import EnvService
    svc = EnvService()
    envs = svc.list_all()
    if not envs:
        click.echo("没有已注册的环境。")
        return
    for e in envs:
        tools = ", ".join((e.get("tools") or {}).keys()) or "-"
        click.echo(f"  {e['name']:20s} tools=[{tools}]  {e.get('description', '')}")


@env_group.command(name="add")
@click.argument("name")
@click.option("--desc", default="", help="描述")
@click.option("--var", multiple=True, help="环境变量 key=value（可多次）")
@click.option("--license", "lics", multiple=True, help="许可证 key=value（可多次）")
def env_svc_add(name: str, desc: str, var: tuple[str, ...], lics: tuple[str, ...]) -> None:
    """注册执行环境"""
    from framework.core.models import EnvironmentSpec
    from framework.services.env_service import EnvService

    variables: dict[str, str] = {}
    for v in var:
        if "=" in v:
            k, val = v.split("=", 1)
            variables[k.strip()] = val.strip()
    licenses: dict[str, str] = {}
    for lic in lics:
        if "=" in lic:
            k, val = lic.split("=", 1)
            licenses[k.strip()] = val.strip()

    spec = EnvironmentSpec(name=name, description=desc, variables=variables, licenses=licenses)
    svc = EnvService()
    svc.register(spec)
    click.echo(f"环境已注册: {name}")


@env_group.command(name="remove")
@click.argument("name")
def env_svc_remove(name: str) -> None:
    """移除环境"""
    from framework.services.env_service import EnvService
    svc = EnvService()
    if svc.remove(name):
        click.echo(f"环境已移除: {name}")
    else:
        click.echo(f"环境不存在: {name}")


@env_group.command(name="provision")
@click.argument("name")
def env_svc_provision(name: str) -> None:
    """装配环境（验证工具链+变量解析）"""
    from framework.services.env_service import EnvService
    svc = EnvService()
    session = svc.provision(name)
    click.echo(f"环境已装配: {name}  状态={session.status}  变量数={len(session.resolved_vars)}")
    for k, v in sorted(session.resolved_vars.items()):
        if k != "PATH":
            click.echo(f"  {k}={v}")


@env_group.command(name="exec")
@click.argument("name")
@click.option("--cmd", required=True, help="要执行的命令")
@click.option("--timeout", default=3600, help="超时时间（秒）")
def env_svc_exec(name: str, cmd: str, timeout: int) -> None:
    """在指定环境中执行命令"""
    from framework.services.env_service import EnvService
    svc = EnvService()
    session = svc.provision(name)
    result = svc.execute_in(session, cmd, timeout=timeout)
    svc.teardown(session)
    status = "成功" if result["success"] else "失败"
    click.echo(f"执行{status} (rc={result['returncode']})")
    if result["stdout"]:
        click.echo(result["stdout"])
    if result["stderr"]:
        click.echo(result["stderr"])


# =========================================================================
# 激励管理
# =========================================================================


@main.group(name="stimulus")
def stimulus_group() -> None:
    """激励管理"""


@stimulus_group.command(name="list")
def stimulus_list() -> None:
    """列出已注册的激励源"""
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    items = svc.list_all()
    if not items:
        click.echo("没有已注册的激励。")
        return
    for s in items:
        click.echo(f"  {s['name']:20s} type={s.get('source_type', '?'):10s} {s.get('description', '')}")


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
    from framework.core.models import StimulusSpec
    from framework.services.stimulus_service import StimulusService
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
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    if svc.remove(name):
        click.echo(f"激励已移除: {name}")
    else:
        click.echo(f"激励不存在: {name}")


@stimulus_group.command(name="acquire")
@click.argument("name")
def stimulus_acquire(name: str) -> None:
    """获取激励产物"""
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    art = svc.acquire(name)
    click.echo(f"状态: {art.status}  路径: {art.local_path}  checksum: {art.checksum}")


# =========================================================================
# 构建管理
# =========================================================================


@main.group(name="build")
def build_group() -> None:
    """构建管理"""


@build_group.command(name="list")
def build_list() -> None:
    """列出已注册的构建配置"""
    from framework.services.build_service import BuildService
    svc = BuildService()
    items = svc.list_all()
    if not items:
        click.echo("没有已注册的构建配置。")
        return
    for b in items:
        click.echo(f"  {b['name']:20s} repo={b.get('repo_name', '-'):15s} build={b.get('build_cmd', '')}")


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
    from framework.core.models import BuildSpec
    from framework.services.build_service import BuildService
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
    from framework.services.build_service import BuildService
    svc = BuildService()
    if svc.remove(name):
        click.echo(f"构建已移除: {name}")
    else:
        click.echo(f"构建配置不存在: {name}")


@build_group.command(name="run")
@click.argument("name")
def build_run(name: str) -> None:
    """执行构建"""
    from framework.services.build_service import BuildService
    svc = BuildService()
    result = svc.build(name)
    status = "成功" if result.status == "success" else "失败"
    click.echo(f"构建{status}: {name} ({result.duration:.1f}s)")
    if result.output_path:
        click.echo(f"产物路径: {result.output_path}")
    if result.message:
        click.echo(f"信息: {result.message}")


# =========================================================================
# 结果管理（增强）
# =========================================================================


@main.group(name="result")
def result_group() -> None:
    """结果管理"""


@result_group.command(name="list")
def result_list() -> None:
    """列出当前结果"""
    from framework.services.result_service import ResultService
    svc = ResultService()
    data = svc.list_results()
    s = data["summary"]
    click.echo(f"汇总: total={s['total']} passed={s['passed']} failed={s['failed']} errors={s['errors']}")


@result_group.command(name="compare")
@click.argument("run_a")
@click.argument("run_b")
def result_compare(run_a: str, run_b: str) -> None:
    """对比两次执行结果"""
    from framework.services.result_service import ResultService
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
    from framework.services.result_service import ResultService
    svc = ResultService()
    count = svc.clean_results()
    click.echo(f"已清理 {count} 个结果文件")


# =========================================================================
# 编排执行
# =========================================================================


@main.command(name="orchestrate")
@click.argument("suite", default="default")
@click.option("-p", "--parallel", default=1, help="并行度")
@click.option("-c", "--config", default="configs/default.yml", help="配置文件")
@click.option("-e", "--env", default="", help="执行环境")
@click.option("--repo", multiple=True, help="代码仓名称（可多次）")
@click.option("--build", "build_names", multiple=True, help="构建名称（可多次）")
@click.option("--stimulus", multiple=True, help="激励名称（可多次）")
@click.option("--snapshot", default="", help="快照 ID")
@click.option("--case", multiple=True, help="用例名称（可多次）")
@click.option("--param", multiple=True, help="参数 key=value（可多次）")
def orchestrate(
    suite: str, parallel: int, config: str, env: str,
    repo: tuple[str, ...], build_names: tuple[str, ...],
    stimulus: tuple[str, ...], snapshot: str,
    case: tuple[str, ...], param: tuple[str, ...],
) -> None:
    """7 步编排执行（代码仓→环境→构建→激励→执行→收集→清理）"""
    from framework.services.execution_orchestrator import (
        ExecutionOrchestrator,
        OrchestrationPlan,
    )

    params: dict[str, str] = {}
    for p in param:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip()] = v.strip()

    plan = OrchestrationPlan(
        suite=suite, config_path=config, parallel=parallel,
        repo_names=list(repo), environment=env,
        build_names=list(build_names), stimulus_names=list(stimulus),
        params=params, snapshot_id=snapshot, case_names=list(case),
    )

    orch = ExecutionOrchestrator()
    report = orch.run(plan)

    click.echo("\n=== 编排执行报告 ===")
    for step in report.steps:
        status = step.get("status", "?")
        detail = step.get("detail", "")
        click.echo(f"  [{status:8s}] {step['step']}" + (f"  ({detail})" if detail else ""))

    if report.suite_result:
        sr = report.suite_result
        click.echo(f"\n结果: total={sr.total} passed={sr.passed} failed={sr.failed} errors={sr.errors}")
    if report.run_id:
        click.echo(f"run_id: {report.run_id}")
    click.echo(f"成功: {'是' if report.success else '否'}")


if __name__ == "__main__":
    main()
