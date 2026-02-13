"""aieffect 命令行接口 - 模块化版本

拆分说明：
- 将原 1082 行的 cli.py 拆分为 13 个模块
- 每个模块负责一组相关的命令
- 降低耦合度，提高可维护性
"""

import click

from framework import __version__

# 导入所有模块
from framework.cli import (
    build,
    cases,
    core,
    deps,
    env,
    history_cmd,
    orchestrate,
    repo,
    result,
    snapshot,
    stimulus,
)


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """aieffect - AI 芯片验证效率集成平台"""


# 注册核心命令
core.register_commands(main)

# 注册依赖管理命令
deps.register_commands(main)

# 注册用例管理命令
cases.register_commands(main)

# 注册快照管理命令
snapshot.register_commands(main)

# 注册历史查询命令
history_cmd.register_commands(main)

# 注册代码仓管理命令
repo.register_commands(main)

# 注册环境管理命令
env.register_commands(main)

# 注册激励管理命令
stimulus.register_commands(main)

# 注册构建管理命令
build.register_commands(main)

# 注册结果管理命令
result.register_commands(main)

# 注册编排执行命令
orchestrate.register_commands(main)


if __name__ == "__main__":
    main()
