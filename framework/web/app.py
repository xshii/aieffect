"""轻量级 Web 看板（基于 Flask）

提供：回归结果查看、依赖包状态、手动触发回归、上传依赖包等功能。

启动方式:
    python -m framework.web.app --port 8888
    或: aieffect dashboard --port 8888
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, render_template_string

logger = logging.getLogger(__name__)

RESULT_DIR = Path("results")
DEPS_REGISTRY = Path("deps/registry.yml")

app = Flask(__name__)


# =============================================================================
# 页面路由
# =============================================================================


@app.route("/")
def index():
    """首页 - 单页看板"""
    return render_template_string(DASHBOARD_HTML)


# =============================================================================
# API 路由
# =============================================================================


@app.route("/api/results")
def api_results():
    """获取回归结果列表"""
    results = []
    if RESULT_DIR.exists():
        for f in sorted(RESULT_DIR.glob("*.json")):
            if f.name == "report.json":
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
    """获取依赖包列表"""
    if not DEPS_REGISTRY.exists():
        return jsonify(packages=[])

    data = yaml.safe_load(DEPS_REGISTRY.read_text()) or {}
    packages = []
    for name, info in (data.get("packages") or {}).items():
        if info:
            packages.append({"name": name, **info})
    return jsonify(packages=packages)


@app.route("/api/run", methods=["POST"])
def api_run():
    """手动触发回归执行"""
    body = request.get_json(silent=True) or {}
    suite = body.get("suite", "default")
    parallel = body.get("parallel", 1)
    config = body.get("config", "configs/default.yml")

    cmd = f"python -m framework.cli run {suite} -p {parallel} -c {config}"
    logger.info("手动触发回归: %s", cmd)

    proc = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    return jsonify(message=f"回归已触发", pid=proc.pid, command=cmd)


@app.route("/api/deps/upload", methods=["POST"])
def api_upload_dep():
    """上传依赖包（通过表单上传文件）"""
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


# =============================================================================
# 看板 HTML 模板
# =============================================================================


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>aieffect 看板</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "Microsoft YaHei", monospace; background: #f5f5f5; color: #333; }
  .header { background: #1a1a2e; color: #fff; padding: 1em 2em; display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 1.4em; }
  .header span { font-size: 0.85em; opacity: 0.7; }
  .container { max-width: 1200px; margin: 0 auto; padding: 1.5em; }

  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1em; margin-bottom: 1.5em; }
  .card { background: #fff; border-radius: 8px; padding: 1.2em; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }
  .card .num { font-size: 2em; font-weight: bold; }
  .card .label { font-size: 0.85em; color: #666; margin-top: 0.3em; }
  .card.pass .num { color: #28a745; }
  .card.fail .num { color: #dc3545; }
  .card.error .num { color: #ffc107; }
  .card.total .num { color: #007bff; }

  .section { background: #fff; border-radius: 8px; padding: 1.2em; margin-bottom: 1.5em; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .section h2 { font-size: 1.1em; margin-bottom: 0.8em; border-bottom: 2px solid #eee; padding-bottom: 0.4em; }

  table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #fafafa; font-weight: 600; }
  .status-passed { color: #28a745; font-weight: bold; }
  .status-failed { color: #dc3545; font-weight: bold; }
  .status-error { color: #ffc107; font-weight: bold; }
  .status-skipped { color: #6c757d; }

  .loading { text-align: center; padding: 2em; color: #999; }
  .btn { background: #007bff; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 0.85em; }
  .btn:hover { background: #0056b3; }
  .btn-success { background: #28a745; }
  .btn-success:hover { background: #218838; }

  .toolbar { display: flex; gap: 0.8em; align-items: center; flex-wrap: wrap; margin-bottom: 1em; }
  .toolbar input, .toolbar select { padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85em; }
  .toolbar label { font-size: 0.85em; color: #555; }

  .upload-form { display: flex; gap: 0.8em; align-items: center; flex-wrap: wrap; }
  .upload-form input { padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85em; }
  .msg { padding: 8px 12px; border-radius: 4px; font-size: 0.85em; margin-top: 0.5em; display: none; }
  .msg.ok { display: block; background: #d4edda; color: #155724; }
  .msg.err { display: block; background: #f8d7da; color: #721c24; }
</style>
</head><body>
<div class="header">
  <div><h1>aieffect 验证看板</h1><span>AI 芯片验证效率集成平台</span></div>
</div>
<div class="container">
  <!-- 汇总卡片 -->
  <div class="cards" id="summary">
    <div class="card total"><div class="num" id="s-total">-</div><div class="label">总计</div></div>
    <div class="card pass"><div class="num" id="s-passed">-</div><div class="label">通过</div></div>
    <div class="card fail"><div class="num" id="s-failed">-</div><div class="label">失败</div></div>
    <div class="card error"><div class="num" id="s-errors">-</div><div class="label">错误</div></div>
  </div>

  <!-- 手动触发回归 -->
  <div class="section">
    <h2>触发回归</h2>
    <div class="toolbar">
      <label>套件:</label><input id="run-suite" value="default" size="12">
      <label>并行度:</label><input id="run-parallel" type="number" value="1" min="1" max="64" size="4">
      <label>配置:</label><input id="run-config" value="configs/default.yml" size="24">
      <button class="btn btn-success" onclick="triggerRun()">执行</button>
    </div>
    <div class="msg" id="run-msg"></div>
  </div>

  <!-- 回归结果 -->
  <div class="section">
    <h2>回归结果 <button class="btn" onclick="loadResults()">刷新</button></h2>
    <div id="results-table"><div class="loading">加载中...</div></div>
  </div>

  <!-- 依赖包状态 -->
  <div class="section">
    <h2>依赖包状态</h2>
    <div id="deps-table"><div class="loading">加载中...</div></div>
  </div>

  <!-- 上传依赖包 -->
  <div class="section">
    <h2>上传依赖包</h2>
    <div class="upload-form">
      <label>包名:</label><input id="up-name" size="15">
      <label>版本:</label><input id="up-version" size="10">
      <input type="file" id="up-file">
      <button class="btn btn-success" onclick="uploadDep()">上传</button>
    </div>
    <div class="msg" id="upload-msg"></div>
  </div>
</div>

<script>
async function loadResults() {
  try {
    const resp = await fetch('/api/results');
    const data = await resp.json();
    const s = data.summary;
    document.getElementById('s-total').textContent = s.total;
    document.getElementById('s-passed').textContent = s.passed;
    document.getElementById('s-failed').textContent = s.failed;
    document.getElementById('s-errors').textContent = s.errors;

    if (data.results.length === 0) {
      document.getElementById('results-table').innerHTML = '<div class="loading">暂无结果数据</div>';
      return;
    }

    let html = '<table><tr><th>用例名</th><th>状态</th><th>耗时</th><th>信息</th></tr>';
    for (const r of data.results) {
      const cls = 'status-' + (r.status || 'unknown');
      html += '<tr><td>' + esc(r.name||'') + '</td><td class="'+cls+'">' + esc(r.status||'') +
              '</td><td>' + (r.duration ? r.duration.toFixed(1)+'s' : '-') +
              '</td><td>' + esc((r.message||'').substring(0,120)) + '</td></tr>';
    }
    html += '</table>';
    document.getElementById('results-table').innerHTML = html;
  } catch(e) {
    document.getElementById('results-table').innerHTML = '<div class="loading">加载失败: '+e+'</div>';
  }
}

async function loadDeps() {
  try {
    const resp = await fetch('/api/deps');
    const data = await resp.json();
    if (!data.packages || data.packages.length === 0) {
      document.getElementById('deps-table').innerHTML = '<div class="loading">暂无依赖包数据</div>';
      return;
    }
    let html = '<table><tr><th>包名</th><th>负责人</th><th>版本</th><th>来源</th><th>说明</th></tr>';
    for (const p of data.packages) {
      html += '<tr><td>'+esc(p.name)+'</td><td>'+esc(p.owner||'-')+'</td><td>'+esc(p.version||'-')+
              '</td><td>'+esc(p.source||'-')+'</td><td>'+esc(p.description||'')+'</td></tr>';
    }
    html += '</table>';
    document.getElementById('deps-table').innerHTML = html;
  } catch(e) {
    document.getElementById('deps-table').innerHTML = '<div class="loading">加载失败: '+e+'</div>';
  }
}

async function triggerRun() {
  const msgEl = document.getElementById('run-msg');
  try {
    const resp = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        suite: document.getElementById('run-suite').value,
        parallel: parseInt(document.getElementById('run-parallel').value),
        config: document.getElementById('run-config').value
      })
    });
    const data = await resp.json();
    msgEl.className = 'msg ok';
    msgEl.textContent = data.message + ' (PID: ' + data.pid + ')';
  } catch(e) {
    msgEl.className = 'msg err';
    msgEl.textContent = '触发失败: ' + e;
  }
}

async function uploadDep() {
  const msgEl = document.getElementById('upload-msg');
  const name = document.getElementById('up-name').value;
  const version = document.getElementById('up-version').value;
  const fileInput = document.getElementById('up-file');

  if (!name || !version || !fileInput.files.length) {
    msgEl.className = 'msg err';
    msgEl.textContent = '请填写包名、版本并选择文件';
    return;
  }

  const form = new FormData();
  form.append('name', name);
  form.append('version', version);
  form.append('file', fileInput.files[0]);

  try {
    const resp = await fetch('/api/deps/upload', { method: 'POST', body: form });
    const data = await resp.json();
    if (data.error) {
      msgEl.className = 'msg err';
      msgEl.textContent = data.error;
    } else {
      msgEl.className = 'msg ok';
      msgEl.textContent = data.message + ' -> ' + data.path;
      loadDeps();
    }
  } catch(e) {
    msgEl.className = 'msg err';
    msgEl.textContent = '上传失败: ' + e;
  }
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

loadResults();
loadDeps();
setInterval(loadResults, 30000);
</script>
</body></html>"""


# =============================================================================
# 服务器启动
# =============================================================================


def run_server(port: int = 8888, debug: bool = False) -> None:
    """启动看板服务器"""
    logger.info("看板已启动: http://localhost:%d", port)
    print(f"aieffect 看板已启动: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    import argparse
    from framework.utils.logger import setup_logging

    parser = argparse.ArgumentParser(description="启动 aieffect 轻量级看板")
    parser.add_argument("--port", type=int, default=8888, help="监听端口")
    parser.add_argument("--debug", action="store_true", help="开启调试模式")
    args = parser.parse_args()

    setup_logging(level="INFO")
    run_server(port=args.port, debug=args.debug)
