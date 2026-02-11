"""构建版本快照管理

将当前的完整构建依赖（EDA 工具版本 + 组件包版本）锁定为一个版本打包节点，
确保每次构建/执行都有明确的版本基线可回溯。

快照存储在 deps/snapshots/<id>.yml
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from framework.utils.yaml_io import load_yaml, save_yaml

logger = logging.getLogger(__name__)


class SnapshotManager:
    """构建版本快照管理器"""

    def __init__(
        self,
        manifest_path: str = "",
        snapshots_dir: str = "",
    ) -> None:
        if not manifest_path or not snapshots_dir:
            from framework.core.config import get_config
            cfg = get_config()
            manifest_path = manifest_path or cfg.manifest
            snapshots_dir = snapshots_dir or cfg.snapshots_dir
        self.manifest_path = Path(manifest_path)
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> dict:
        return load_yaml(self.manifest_path)

    def create(self, description: str = "", snapshot_id: str | None = None) -> dict:
        """从当前清单创建版本快照"""
        manifest = self._load_manifest()
        now = datetime.now(tz=timezone.utc)

        if not snapshot_id:
            seq = len(list(self.snapshots_dir.glob("*.yml"))) + 1
            snapshot_id = now.strftime(f"snap-%Y%m%d-{seq:03d}")

        snapshot = {
            "id": snapshot_id,
            "created_at": now.isoformat(),
            "description": description,
            "python": manifest.get("python", ""),
            "eda_tools": manifest.get("eda_tools", {}),
            "packages": manifest.get("packages", {}),
            "license": manifest.get("license", {}),
        }

        out_path = self.snapshots_dir / f"{snapshot_id}.yml"
        save_yaml(out_path, snapshot)

        logger.info("快照已创建: %s -> %s", snapshot_id, out_path)
        return snapshot

    def list_snapshots(self) -> list[dict]:
        """列出所有已有快照的摘要信息"""
        snapshots = []
        for f in sorted(self.snapshots_dir.glob("*.yml")):
            data = load_yaml(f)
            snapshots.append({
                "id": data.get("id", f.stem),
                "created_at": data.get("created_at", ""),
                "description": data.get("description", ""),
            })
        return snapshots

    def get(self, snapshot_id: str) -> dict | None:
        """加载指定快照的完整内容"""
        path = self.snapshots_dir / f"{snapshot_id}.yml"
        if not path.exists():
            return None
        return load_yaml(path)

    def restore(self, snapshot_id: str) -> bool:
        """将指定快照恢复为当前清单"""
        snapshot = self.get(snapshot_id)
        if snapshot is None:
            logger.error("快照不存在: %s", snapshot_id)
            return False

        manifest = self._load_manifest()
        manifest["python"] = snapshot.get("python", manifest.get("python", ""))
        manifest["eda_tools"] = snapshot.get("eda_tools", manifest.get("eda_tools", {}))
        manifest["packages"] = snapshot.get("packages", manifest.get("packages", {}))
        manifest["license"] = snapshot.get("license", manifest.get("license", {}))

        save_yaml(self.manifest_path, manifest)

        logger.info("快照已恢复: %s -> %s", snapshot_id, self.manifest_path)
        return True

    def diff(self, id_a: str, id_b: str) -> dict:
        """比较两个快照之间的差异"""
        a = self.get(id_a) or {}
        b = self.get(id_b) or {}

        def _diff_section(section: str) -> list[dict]:
            items_a, items_b = a.get(section) or {}, b.get(section) or {}
            changes = []
            for name in sorted(set(items_a) | set(items_b)):
                ver_a = (items_a.get(name) or {}).get("version", "")
                ver_b = (items_b.get(name) or {}).get("version", "")
                if ver_a != ver_b:
                    changes.append({"name": name, id_a: ver_a or "(无)", id_b: ver_b or "(无)"})
            return changes

        return {"packages": _diff_section("packages"), "eda_tools": _diff_section("eda_tools")}
