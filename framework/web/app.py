"""轻量级 Web 看板（基于 Flask）

提供：回归结果查看、依赖包状态、手动触发回归、上传依赖包。

启动方式: aieffect dashboard --port 8888
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

RESULT_DIR = Path("results")
DEPS_MANIFEST = Path("deps/manifest.yml")

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/results")
def api_results():
    results = []
    if RESULT_DIR.exists():
        for f in sorted(RESULT_DIR.glob("*.json")):
            if f.name.startswith("report"):
                continue
            try:
                results.append(json.loads(f.read_text()))
            except json.JSONDecodeError:
                pass

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("status") == "passed"),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
        "errors": sum(1 for r in results if r.get("status") == "error"),
    }
    return jsonify(summary=summary, results=results)


@app.route("/api/deps")
def api_deps():
    if not DEPS_MANIFEST.exists():
        return jsonify(packages=[])

    data = yaml.safe_load(DEPS_MANIFEST.read_text()) or {}
    packages = []
    for name, info in (data.get("packages") or {}).items():
        if info:
            packages.append({"name": name, **info})
    return jsonify(packages=packages)


_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_safe_name(value: str, field: str) -> str:
    """校验参数仅包含安全字符，防止命令注入"""
    value = str(value).strip()
    if not _SAFE_NAME_RE.match(value):
        raise ValueError(f"参数 '{field}' 包含非法字符: {value}")
    return value


def _wait_and_log(proc: subprocess.Popen, cmd: list[str]) -> None:
    """后台线程等待子进程结束，避免僵尸进程"""
    try:
        stdout, _ = proc.communicate()
        logger.info("回归完成 (pid=%d, rc=%d): %s", proc.pid, proc.returncode, cmd)
        if proc.returncode != 0 and stdout:
            logger.warning("回归输出 (pid=%d):\n%s", proc.pid, stdout[:2000])
    except Exception:
        logger.exception("等待回归进程 (pid=%d) 时出错", proc.pid)


@app.route("/api/run", methods=["POST"])
def api_run():
    body = request.get_json(silent=True) or {}

    try:
        suite = _validate_safe_name(body.get("suite", "default"), "suite")
        parallel = int(body.get("parallel", 1))
        raw_config = body.get("config", "configs/default.yml").replace("/", "_").replace(".", "_")
        config = _validate_safe_name(raw_config, "config")
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400

    # 还原 config 路径：约束在 configs/ 目录下
    config_path = f"configs/{config.replace('_', '/')}"
    config_file = Path(config_path)
    if not config_file.suffix:
        config_path += ".yml"

    cmd = ["aieffect", "run", suite, "-p", str(parallel), "-c", config_path]
    logger.info("手动触发回归: %s", cmd)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # 后台线程回收子进程，避免僵尸进程
    threading.Thread(target=_wait_and_log, args=(proc, cmd), daemon=True).start()
    return jsonify(message="回归已触发", pid=proc.pid, command=" ".join(cmd))


@app.route("/api/deps/upload", methods=["POST"])
def api_upload_dep():
    name = request.form.get("name", "")
    version = request.form.get("version", "")
    file = request.files.get("file")

    if not name or not version or not file or not file.filename:
        return jsonify(error="需要提供 name、version 和 file"), 400

    # 校验 name 和 version，防止路径穿越
    try:
        name = _validate_safe_name(name, "name")
        version = _validate_safe_name(version, "version")
    except ValueError as e:
        return jsonify(error=str(e)), 400

    safe_name = secure_filename(file.filename)
    if not safe_name:
        return jsonify(error="文件名不合法"), 400

    base_dir = Path("deps/packages").resolve()
    upload_dir = (base_dir / name / version).resolve()

    # 确保最终路径在预期目录下
    if not str(upload_dir).startswith(str(base_dir)):
        return jsonify(error="路径不合法"), 400

    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_name
    file.save(str(dest))

    logger.info("依赖包已上传: %s@%s -> %s", name, version, dest)
    return jsonify(message=f"已上传 {name}@{version}", path=str(dest))


def run_server(port: int = 8888, debug: bool = False, host: str = "127.0.0.1") -> None:
    print(f"aieffect 看板已启动: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
