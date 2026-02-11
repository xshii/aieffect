"""Gunicorn 生产配置

用法:
  gunicorn --config deploy/gunicorn.conf.py framework.web.app:app
"""

import multiprocessing
import os

# ---------- 网络 ----------
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8888")

# ---------- 并发 ----------
workers = int(os.getenv("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 8)))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_class = "gthread"
timeout = 120

# ---------- 日志 ----------
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# ---------- 进程管理 ----------
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
