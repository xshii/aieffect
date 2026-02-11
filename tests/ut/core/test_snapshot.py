"""构建版本快照测试"""

from pathlib import Path

import yaml

from framework.core.snapshot import SnapshotManager


def _create_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "manifest.yml"
    manifest.write_text(yaml.dump({
        "python": "3.10",
        "eda_tools": {"vcs": {"version": "U-2023.03"}},
        "packages": {"model_lib": {"version": "v1.0", "owner": "team-a", "source": "api"}},
        "license": {"synopsys": "27000@lic"},
    }))
    return manifest


class TestSnapshotManager:
    def test_create_and_list(self, tmp_path: Path) -> None:
        manifest = _create_manifest(tmp_path)
        snap_dir = tmp_path / "snapshots"
        sm = SnapshotManager(manifest_path=str(manifest), snapshots_dir=str(snap_dir))

        snap = sm.create(description="初始版本")
        assert snap["id"].startswith("snap-")
        assert snap["python"] == "3.10"

        snaps = sm.list_snapshots()
        assert len(snaps) == 1

    def test_get(self, tmp_path: Path) -> None:
        manifest = _create_manifest(tmp_path)
        snap_dir = tmp_path / "snapshots"
        sm = SnapshotManager(manifest_path=str(manifest), snapshots_dir=str(snap_dir))

        sm.create(snapshot_id="test-snap-001")
        snap = sm.get("test-snap-001")
        assert snap is not None
        assert snap["id"] == "test-snap-001"
        assert "model_lib" in (snap.get("packages") or {})

    def test_restore(self, tmp_path: Path) -> None:
        manifest = _create_manifest(tmp_path)
        snap_dir = tmp_path / "snapshots"
        sm = SnapshotManager(manifest_path=str(manifest), snapshots_dir=str(snap_dir))

        sm.create(snapshot_id="snap-before")

        # 修改清单
        data = yaml.safe_load(manifest.read_text())
        data["packages"]["model_lib"]["version"] = "v2.0"
        manifest.write_text(yaml.dump(data))

        # 恢复
        assert sm.restore("snap-before") is True
        restored = yaml.safe_load(manifest.read_text())
        assert restored["packages"]["model_lib"]["version"] == "v1.0"

    def test_diff(self, tmp_path: Path) -> None:
        manifest = _create_manifest(tmp_path)
        snap_dir = tmp_path / "snapshots"
        sm = SnapshotManager(manifest_path=str(manifest), snapshots_dir=str(snap_dir))

        sm.create(snapshot_id="v1")

        data = yaml.safe_load(manifest.read_text())
        data["packages"]["model_lib"]["version"] = "v2.0"
        manifest.write_text(yaml.dump(data))
        sm.create(snapshot_id="v2")

        changes = sm.diff("v1", "v2")
        assert len(changes["packages"]) == 1
        assert changes["packages"][0]["name"] == "model_lib"

    def test_nonexistent_snapshot(self, tmp_path: Path) -> None:
        snap_dir = tmp_path / "snapshots"
        sm = SnapshotManager(snapshots_dir=str(snap_dir))
        assert sm.get("nonexistent") is None
        assert sm.restore("nonexistent") is False
