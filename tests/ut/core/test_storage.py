"""存储层测试"""

import json
import time
from pathlib import Path
from unittest.mock import patch

from framework.core.storage import LocalStorage, RemoteStorage, create_storage


class TestLocalStorage:
    def test_put_get(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        storage.put("results", "run-001", {"status": "passed"})

        data = storage.get("results", "run-001")
        assert data is not None
        assert data["status"] == "passed"
        assert data["_key"] == "run-001"
        assert data["_namespace"] == "results"

    def test_list_keys(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        storage.put("ns", "a", {"x": 1})
        storage.put("ns", "b", {"x": 2})

        keys = storage.list_keys("ns")
        assert sorted(keys) == ["a", "b"]

    def test_delete(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        storage.put("ns", "key1", {"x": 1})
        assert storage.delete("ns", "key1") is True
        assert storage.get("ns", "key1") is None
        assert storage.delete("ns", "key1") is False

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        assert storage.get("ns", "nothing") is None

    def test_empty_namespace(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        assert storage.list_keys("empty") == []


class TestRemoteStorage:
    def test_local_cache(self, tmp_path: Path) -> None:
        """远端存储的本地缓存功能"""
        rs = RemoteStorage(
            api_url="http://localhost:9999",
            cache_dir=str(tmp_path / "cache"),
            cache_days=7,
        )
        rs.put("ns", "key1", {"v": 42})
        data = rs.get("ns", "key1")
        assert data is not None
        assert data["v"] == 42

    def test_list_keys(self, tmp_path: Path) -> None:
        rs = RemoteStorage(api_url="http://localhost:9999", cache_dir=str(tmp_path / "cache"))
        rs.put("ns", "a", {})
        rs.put("ns", "b", {})
        assert sorted(rs.list_keys("ns")) == ["a", "b"]

    def test_get_remote_fallback_failure(self, tmp_path: Path) -> None:
        """缓存未命中且远端获取失败时返回 None"""
        rs = RemoteStorage(
            api_url="http://localhost:9999",
            cache_dir=str(tmp_path / "cache"),
        )
        # 没写入缓存，远端不可达
        assert rs.get("ns", "missing") is None

    def test_flush_empty(self, tmp_path: Path) -> None:
        """空缓存 flush 返回 0/0"""
        rs = RemoteStorage(
            api_url="http://localhost:9999",
            cache_dir=str(tmp_path / "cache"),
        )
        result = rs.flush()
        assert result == {"forwarded": 0, "failed": 0}

    def test_flush_skips_recent(self, tmp_path: Path) -> None:
        """flush 不转发未过期的数据"""
        rs = RemoteStorage(
            api_url="http://localhost:9999",
            cache_dir=str(tmp_path / "cache"),
            cache_days=7,
        )
        rs.put("ns", "fresh", {"value": 1})
        result = rs.flush()
        assert result == {"forwarded": 0, "failed": 0}
        # 数据仍保留在缓存中
        assert rs.cache.get("ns", "fresh") is not None

    def test_flush_forwards_expired(self, tmp_path: Path) -> None:
        """flush 转发已过期数据，远端失败计入 failed"""
        rs = RemoteStorage(
            api_url="http://localhost:9999",
            cache_dir=str(tmp_path / "cache"),
            cache_days=0,
        )
        rs.put("ns", "old", {"value": 1})
        # 伪造一个过期的 _stored_at
        cache_file = rs.cache._path("ns", "old")
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        data["_stored_at"] = time.time() - 999999
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        # 远端不可达，所以 forward 会失败
        result = rs.flush()
        assert result["failed"] == 1
        assert result["forwarded"] == 0

    def test_forward_one_success(self, tmp_path: Path) -> None:
        """_forward_one 成功时删除本地文件"""
        rs = RemoteStorage(
            api_url="http://localhost:9999",
            cache_dir=str(tmp_path / "cache"),
        )
        rs.put("ns", "k", {"v": 1})
        file_path = rs.cache._path("ns", "k")
        data = json.loads(file_path.read_text(encoding="utf-8"))

        with patch("urllib.request.urlopen"):
            ok = rs._forward_one("ns", file_path, data)
        assert ok is True
        assert not file_path.exists()


class TestPathTraversalDefense:
    def test_dotdot_in_key_sanitized(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        storage.put("ns", "../../etc/passwd", {"evil": True})
        # key 中的 .. 和 / 被替换为 _
        files = list((tmp_path / "store" / "ns").glob("*.json"))
        assert len(files) == 1
        assert ".." not in files[0].name
        assert "/" not in files[0].name

    def test_slash_in_key_sanitized(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        storage.put("ns", "a/b/c", {"x": 1})
        data = storage.get("ns", "a/b/c")
        assert data is not None
        assert data["x"] == 1
        # 不应在 ns 下创建子目录
        assert not (tmp_path / "store" / "ns" / "a").exists()

    def test_dotdot_in_namespace(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        storage.put("../secret", "k", {"x": 1})
        # 数据应存在 store/../secret/ 下，但不应逃逸出 store 的父目录
        data = storage.get("../secret", "k")
        assert data is not None


class TestCreateStorage:
    def test_default_local(self) -> None:
        storage = create_storage()
        assert isinstance(storage, LocalStorage)

    def test_explicit_local(self) -> None:
        storage = create_storage({"backend": "local", "local_dir": "/tmp/test_store"})
        assert isinstance(storage, LocalStorage)

    def test_remote(self) -> None:
        storage = create_storage({
            "backend": "remote",
            "remote": {"api_url": "http://example.com/api", "cache_days": 3},
        })
        assert isinstance(storage, RemoteStorage)
