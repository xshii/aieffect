"""aieffect 命令行接口

CLI 按领域拆分为子模块，每个模块注册自己的命令到 main group。
"""

import os
from typing import Any

import click

from framework import __version__
from framework.services.container import get_container
from framework.utils.logger import setup_logging


def _svc() -> Any:
    """获取全局服务容器的快捷方式"""
    return get_container()


def _parse_kv_pairs(pairs: tuple[str, ...]) -> dict[str, str]:
    """解析 key=value 参数对"""
    result: dict[str, str] = {}
    for p in pairs:
        if "=" in p:
            k, v = p.split("=", 1)
            result[k.strip()] = v.strip()
    return result


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """aieffect - AI 芯片验证效率集成平台"""
    setup_logging(
        level=os.getenv("AIEFFECT_LOG_LEVEL", "INFO"),
        json_output=os.getenv("AIEFFECT_LOG_JSON", "") == "1",
    )


# 注册各领域子命令
from framework.cli.cmd_run import register as _reg_run  # noqa: E402
from framework.cli.cmd_deps import register as _reg_deps  # noqa: E402
from framework.cli.cmd_cases import register as _reg_cases  # noqa: E402
from framework.cli.cmd_repo import register as _reg_repo  # noqa: E402
from framework.cli.cmd_env import register as _reg_env  # noqa: E402
from framework.cli.cmd_stimulus import register as _reg_stimulus  # noqa: E402
from framework.cli.cmd_build import register as _reg_build  # noqa: E402
from framework.cli.cmd_result import register as _reg_result  # noqa: E402
from framework.cli.cmd_misc import register as _reg_misc  # noqa: E402

_reg_run(main)
_reg_deps(main)
_reg_cases(main)
_reg_repo(main)
_reg_env(main)
_reg_stimulus(main)
_reg_build(main)
_reg_result(main)
_reg_misc(main)
