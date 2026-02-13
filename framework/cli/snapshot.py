"""构建版本快照管理命令"""

import click

from framework.core.snapshot import SnapshotManager


def register_commands(main: click.Group) -> None:
    """注册快照管理相关命令"""
    main.add_command(snapshot_group)


@click.group(name="snapshot")
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
