"""轻量级 Web 看板（基于 Flask）- 主应用

职责:
- Flask 应用初始化
- Blueprint 注册
- 全局错误处理
- 服务器启动

重构说明:
- 原 424 行拆分为 8 个模块
- 7 个新 Blueprint (routes/): core, cases, snapshots, history, utils, results, orchestrate
- 4 个已有 Blueprint (blueprints/): envs, stimuli, builds, repos
- 主应用 app.py (106 行): 应用配置和 Blueprint 注册

提供：回归结果查看、依赖包状态、上传依赖包、
      用例表单管理、执行历史、日志检查、资源状态、外部结果录入、
      存储对接、环境管理、激励管理、构建管理、结果管理、编排执行。

Blueprint 架构:
  # 已有 Blueprint (blueprints/)
  envs_bp     — /api/envs/**     (13 routes)
  stimuli_bp  — /api/stimuli/**  (13 routes)
  builds_bp   — /api/builds/**   (5 routes)
  repos_bp    — /api/repos/**    (6 routes)

  # 新增 Blueprint (routes/)
  core_bp        — /api/results, /api/deps (3 routes)
  cases_bp       — /api/cases/**         (5 routes)
  snapshots_bp   — /api/snapshots/**     (4 routes)
  history_bp     — /api/history/**       (3 routes)
  utils_bp       — /api/check-log, storage, resource (5 routes)
  results_bp     — /api/results/**       (3 routes)
  orchestrate_bp — /api/orchestrate      (1 route)

启动方式: aieffect dashboard --port 8888
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template
from werkzeug.exceptions import HTTPException

# 已有 Blueprint
from framework.web.blueprints.builds_bp import builds_bp
from framework.web.blueprints.envs_bp import envs_bp
from framework.web.blueprints.repos_bp import repos_bp
from framework.web.blueprints.stimuli_bp import stimuli_bp

# 新增 Blueprint
from framework.web.routes import (
    cases_bp,
    core_bp,
    history_bp,
    orchestrate_bp,
    results_bp,
    snapshots_bp,
    utils_bp,
)

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# 注册已有 Blueprint
app.register_blueprint(envs_bp)
app.register_blueprint(stimuli_bp)
app.register_blueprint(builds_bp)
app.register_blueprint(repos_bp)

# 注册新增 Blueprint
app.register_blueprint(core_bp)
app.register_blueprint(cases_bp)
app.register_blueprint(snapshots_bp)
app.register_blueprint(history_bp)
app.register_blueprint(utils_bp)
app.register_blueprint(results_bp)
app.register_blueprint(orchestrate_bp)


# =========================================================================
# 全局错误处理
# =========================================================================


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    return jsonify(error=exc.description), exc.code


@app.errorhandler(Exception)
def handle_generic_exception(exc):  # noqa: ARG001
    logger.exception("未处理的异常")
    return jsonify(error="服务器内部错误"), 500


@app.route("/")
def index():
    return render_template("dashboard.html")


# =========================================================================
# 服务器启动
# =========================================================================


def run_server(port: int = 8888, debug: bool = False, host: str = "127.0.0.1") -> None:
    logger.info("aieffect 看板已启动: http://%s:%d", host, port)
    app.run(host=host, port=port, debug=debug)
