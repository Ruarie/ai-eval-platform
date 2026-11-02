"""把适配层源码目录加入导入路径，使 ``pytest`` 可直接导入 ``adapter`` 包。

该文件与 ``tests/`` 不进入镜像（Dockerfile 只 COPY ``adapter`` 与 ``app.py``），
因此不会影响运行镜像体积。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
