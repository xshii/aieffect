"""轻量级 Web 看板（基于 Flask）

提供：回归结果查看、依赖包状态、手动触发回归、上传依赖包。

启动方式: aieffect dashboard --port 8888
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

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


@app.route("/api/run", methods=["POST"])
def api_run():
    body = request.get_json(silent=True) or {}
    suite = body.get("suite", "default")
    parallel = body.get("parallel", 1)
    config = body.get("config", "configs/default.yml")

    cmd = f"aieffect run {suite} -p {parallel} -c {config}"
    logger.info("手动触发回归: %s", cmd)

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return jsonify(message="回归已触发", pid=proc.pid, command=cmd)


@app.route("/api/deps/upload", methods=["POST"])
def api_upload_dep():
    name = request.form.get("name", "")
    version = request.form.get("version", "")
    file = request.files.get("file")

    if not name or not version or not file:
        return jsonify(error="需要提供 name、version 和 file"), 400

    upload_dir = Path("deps/packages") / name / version
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename
    file.save(str(dest))

    logger.info("依赖包已上传: %s@%s -> %s", name, version, dest)
    return jsonify(message=f"已上传 {name}@{version}", path=str(dest))


def run_server(port: int = 8888, debug: bool = False) -> None:
    print(f"aieffect 看板已启动: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
