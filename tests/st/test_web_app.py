"""Web API 端点测试"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.web.app import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """创建 Flask 测试客户端，临时数据目录"""
    import framework.core.config as cfgmod
    from framework.services.container import reset_container
    cfg = cfgmod.Config(
        result_dir=str(tmp_path / "results"),
        manifest=str(tmp_path / "manifest.yml"),
    )
    monkeypatch.setattr(cfgmod, "_current", cfg)
    reset_container()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    reset_container()


class TestGlobalErrorHandlers:
    def test_404_returns_json(self, client) -> None:
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_405_returns_json(self, client) -> None:
        resp = client.delete("/api/results")
        assert resp.status_code == 405
        data = resp.get_json()
        assert "error" in data


class TestApiResults:
    def test_empty_results(self, client) -> None:
        resp = client.get("/api/results")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["summary"]["total"] == 0
        assert data["results"] == []

    def test_with_result_files(self, client, tmp_path: Path) -> None:
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        (result_dir / "case1.json").write_text(
            json.dumps({"name": "tc1", "status": "passed"}),
            encoding="utf-8",
        )
        resp = client.get("/api/results")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["summary"]["total"] == 1
        assert data["summary"]["passed"] == 1


class TestApiRun:
    def test_invalid_suite_name(self, client) -> None:
        resp = client.post(
            "/api/run",
            json={"suite": "../../etc/passwd"},
        )
        assert resp.status_code == 400

    def test_invalid_parallel_uses_default(self, client, monkeypatch) -> None:
        """非数字 parallel 应回退到默认值而非 500"""
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd

            class FakeProc:
                pid = 12345

                def communicate(self):
                    return "", ""

                @property
                def returncode(self):
                    return 0

            return FakeProc()

        monkeypatch.setattr("framework.web.app.subprocess.Popen", fake_popen)
        resp = client.post(
            "/api/run",
            json={"suite": "default", "parallel": "abc"},
        )
        assert resp.status_code == 200
        # parallel should fallback to 1
        assert "-p" in captured["cmd"]
        idx = captured["cmd"].index("-p")
        assert captured["cmd"][idx + 1] == "1"

    def test_config_path_traversal_blocked(self, client) -> None:
        resp = client.post(
            "/api/run",
            json={"suite": "default", "config": "../../etc/passwd"},
        )
        assert resp.status_code == 400
        assert "不合法" in resp.get_json()["error"]


class TestApiDeps:
    def test_empty_deps(self, client) -> None:
        resp = client.get("/api/deps")
        assert resp.status_code == 200
        assert resp.get_json()["packages"] == []


class TestApiHistory:
    def test_invalid_limit_uses_default(self, client, monkeypatch) -> None:
        """limit 非数字时不崩溃"""
        from framework.core.history import HistoryManager

        monkeypatch.setattr(
            HistoryManager, "_load", lambda self: [],
        )
        resp = client.get("/api/history?limit=abc")
        assert resp.status_code == 200


class TestStorageValidation:
    def test_namespace_with_dots_blocked(self, client) -> None:
        resp = client.get("/api/storage/bad.ns")
        assert resp.status_code == 400
        assert "非法字符" in resp.get_json()["error"]

    def test_key_with_dots_blocked(self, client) -> None:
        resp = client.get("/api/storage/ns/bad.key")
        assert resp.status_code == 400
        assert "非法字符" in resp.get_json()["error"]

    def test_valid_storage_put_get(self, client, monkeypatch, tmp_path) -> None:
        from framework.core.storage import LocalStorage

        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        monkeypatch.setattr(
            "framework.core.storage.create_storage",
            lambda *a, **kw: storage,
        )
        resp = client.put(
            "/api/storage/myns/mykey",
            json={"value": 42},
        )
        assert resp.status_code == 200

        resp = client.get("/api/storage/myns/mykey")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["value"] == 42

    def test_storage_list(self, client, monkeypatch, tmp_path) -> None:
        from framework.core.storage import LocalStorage

        storage = LocalStorage(base_dir=str(tmp_path / "store"))
        storage.put("ns", "k1", {"a": 1})
        monkeypatch.setattr(
            "framework.core.storage.create_storage",
            lambda *a, **kw: storage,
        )
        resp = client.get("/api/storage/ns")
        assert resp.status_code == 200
        assert "k1" in resp.get_json()["keys"]


class TestUploadDep:
    def test_missing_fields(self, client) -> None:
        resp = client.post("/api/deps/upload")
        assert resp.status_code == 400

    def test_invalid_name(self, client) -> None:
        from io import BytesIO

        resp = client.post(
            "/api/deps/upload",
            data={
                "name": "../bad",
                "version": "1.0",
                "file": (BytesIO(b"data"), "pkg.tar.gz"),
            },
        )
        assert resp.status_code == 400
