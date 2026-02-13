"""aieffect 命令行接口 - 模块化版本

拆分说明：
- 将原 1062 行的 cli.py 拆分为多个模块
- 每个模块负责一组相关的命令
- 降低耦合度，提高可维护性
"""

import click

from framework import __version__

# 导入已拆分的模块
from framework.cli import cases, core, deps, history_cmd, snapshot

# TODO: 继续拆分以下模块
# from framework.cli import repo, env, stimulus, build, result, orchestrate


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


# TODO: 继续注册其他模块的命令
# repo.register_commands(main)
# env.register_commands(main)
# stimulus.register_commands(main)
# build.register_commands(main)
# result.register_commands(main)
# orchestrate.register_commands(main)


if __name__ == "__main__":
    main()
