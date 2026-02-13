"""快照管理 API Blueprint

职责:
- 快照 CRUD 操作
- 快照恢复功能
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

snapshots_bp = Blueprint("snapshots", __name__, url_prefix="/api/snapshots")


@snapshots_bp.route("", methods=["GET"])
def api_snapshots_list():
    """获取快照列表"""
    from framework.core.snapshot import SnapshotManager
    return jsonify(snapshots=SnapshotManager().list_snapshots())


@snapshots_bp.route("", methods=["POST"])
def api_snapshots_create():
    """创建新快照"""
    from framework.core.snapshot import SnapshotManager
    body = request.get_json(silent=True) or {}
    snap = SnapshotManager().create(
        description=body.get("description", ""),
        snapshot_id=body.get("id"),
    )
    return jsonify(message=f"快照已创建: {snap['id']}", snapshot=snap)


@snapshots_bp.route("/<snapshot_id>", methods=["GET"])
def api_snapshots_get(snapshot_id: str):
    """获取快照详情"""
    from framework.core.snapshot import SnapshotManager
    snap = SnapshotManager().get(snapshot_id)
    if snap is None:
        return jsonify(error="快照不存在"), 404
    return jsonify(snapshot=snap)


@snapshots_bp.route("/<snapshot_id>/restore", methods=["POST"])
def api_snapshots_restore(snapshot_id: str):
    """恢复快照"""
    from framework.core.snapshot import SnapshotManager
    if SnapshotManager().restore(snapshot_id):
        return jsonify(message=f"快照已恢复: {snapshot_id}")
    return jsonify(error="快照不存在"), 404
