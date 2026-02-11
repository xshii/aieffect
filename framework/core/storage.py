"""存储层抽象 - 支持本地存储与远端 REST API 对接

两种后端：
  - local:  本地文件系统（默认）
  - remote: 对接外部存储 REST API，本地缓存 N 天后转发

远端存储流程：
  1. 写入时先存本地缓存
  2. 异步/延迟转发到远端 REST API
  3. 读取时优先查本地缓存，缓存未命中则从远端获取
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

SECONDS_PER_DAY = 86400


class LocalStorage:
    """本地文件系统存储"""

    def __init__(self, base_dir: str = "") -> None:
        if not base_dir:
            from framework.core.config import get_config
            base_dir = get_config().storage_dir
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, namespace: str, key: str) -> Path:
        # 安全处理 key，避免路径穿越
        safe_key = key.replace("/", "_").replace("..", "_")
        ns_dir = self.base_dir / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        return ns_dir / f"{safe_key}.json"

    def put(self, namespace: str, key: str, data: dict) -> str:
        """存储数据，返回存储路径"""
        path = self._path(namespace, key)
        data_with_meta = {
            "_key": key,
            "_namespace": namespace,
            "_stored_at": time.time(),
            **data,
        }
        path.write_text(
            json.dumps(data_with_meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("本地存储: %s/%s -> %s", namespace, key, path)
        return str(path)

    def get(self, namespace: str, key: str) -> dict[str, object] | None:
        """读取数据"""
        path = self._path(namespace, key)
        if not path.exists():
            return None
        result: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        return result

    def list_keys(self, namespace: str) -> list[str]:
        """列出命名空间下的所有 key"""
        ns_dir = self.base_dir / namespace
        if not ns_dir.exists():
            return []
        return [f.stem for f in sorted(ns_dir.glob("*.json"))]

    def delete(self, namespace: str, key: str) -> bool:
        """删除数据"""
        path = self._path(namespace, key)
        if path.exists():
            path.unlink()
            return True
        return False


class RemoteStorage:
    """远端 REST API 存储，带本地缓存

    缓存策略：写入时先存本地，读取优先走本地缓存。
    转发逻辑：通过 flush 方法将过期缓存推送到远端。
    """

    def __init__(
        self,
        api_url: str,
        cache_dir: str = "data/cache",
        cache_days: int = 7,
    ) -> None:
        from framework.utils.net import validate_url_scheme
        validate_url_scheme(api_url, context="RemoteStorage api_url")
        self.api_url = api_url.rstrip("/")
        self.cache = LocalStorage(cache_dir)
        self.cache_days = cache_days

    def put(self, namespace: str, key: str, data: dict) -> str:
        """写入本地缓存"""
        return self.cache.put(namespace, key, data)

    def get(self, namespace: str, key: str) -> dict[str, object] | None:
        """优先从缓存读取，未命中则从远端获取"""
        cached = self.cache.get(namespace, key)
        if cached is not None:
            return cached

        # 远端获取
        url = f"{self.api_url}/{namespace}/{key}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:  # nosec B310
                data: dict[str, object] = json.loads(resp.read().decode())
            # 写入缓存
            self.cache.put(namespace, key, data)
            return data
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.error("远端获取失败: %s - %s", url, e)
            return None

    def list_keys(self, namespace: str) -> list[str]:
        """列出缓存中的 key（不查远端）"""
        return self.cache.list_keys(namespace)

    def _forward_one(self, namespace: str, file_path: Path, data: dict) -> bool:
        """转发一条数据到远端，成功时删除本地文件"""
        key = data.get("_key", file_path.stem)
        url = f"{self.api_url}/{namespace}/{key}"
        payload = json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request(
            url, data=payload, method="PUT",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15):  # nosec B310
                pass
            file_path.unlink()
            logger.info("已转发: %s/%s", namespace, key)
            return True
        except (urllib.error.URLError, OSError) as e:
            logger.error("转发失败: %s - %s", url, e)
            return False

    def flush(self) -> dict[str, int]:
        """将超过缓存天数的数据转发到远端 REST API，返回统计"""
        cutoff = time.time() - self.cache_days * SECONDS_PER_DAY
        forwarded = failed = 0
        base = self.cache.base_dir
        if not base.exists():
            return {"forwarded": 0, "failed": 0}

        for ns_dir in base.iterdir():
            if not ns_dir.is_dir():
                continue
            for f in ns_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if data.get("_stored_at", 0) > cutoff:
                    continue
                if self._forward_one(ns_dir.name, f, data):
                    forwarded += 1
                else:
                    failed += 1

        logger.info("缓存转发完成: forwarded=%d, failed=%d", forwarded, failed)
        return {"forwarded": forwarded, "failed": failed}


def create_storage(config: dict | None = None) -> LocalStorage | RemoteStorage:
    """根据配置创建存储后端"""
    if config is None:
        config = {}

    backend = config.get("backend", "local")
    if backend == "remote":
        remote_cfg = config.get("remote", {})
        return RemoteStorage(
            api_url=remote_cfg.get("api_url", ""),
            cache_dir=remote_cfg.get("cache_dir", "data/cache"),
            cache_days=remote_cfg.get("cache_days", 7),
        )
    return LocalStorage(config.get("local_dir", ""))
