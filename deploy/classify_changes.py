#!/usr/bin/env python3
"""按改动文件判断该跑哪些 CI 作业（PR 阶段用）。

GitHub Actions 的 `paths` 只能挂在 workflow 级别，粒度太粗：一个 PR 改了前端，
workflow 会启动，但 backend（96s）、frontend（410s）该不该跑，得按实际改动决定。

用法：
    git diff --name-only BASE HEAD | python3 deploy/classify_changes.py >> "$GITHUB_OUTPUT"

输出四行 `key=true|false`：backend / frontend / deploy / migrations。
`.github/**` 与守卫脚本自身视为「全量」——改 CI 配置时应该把所有作业都验一遍。
"""

from __future__ import annotations

import sys
from collections.abc import Iterable

# 改了这些路径就当成「配置面」，四个作业全开。
CONFIG_PATTERNS = (".github/", "deploy/classify_changes.py")


def classify(paths: Iterable[str]) -> dict[str, bool]:
    """返回每个作业是否需要运行。"""
    files = [p.strip().replace("\\", "/") for p in paths if p.strip()]
    result = {"backend": False, "frontend": False, "deploy": False, "migrations": False}

    for path in files:
        if path.startswith(CONFIG_PATTERNS):
            return dict.fromkeys(result, True)
        if path.startswith("backend/api/migrations/"):
            result["migrations"] = True
            result["backend"] = True
        elif path.startswith("backend/"):
            result["backend"] = True
        elif path.startswith("frontend/"):
            result["frontend"] = True
        elif path.startswith("deploy/") or path.startswith("docker-compose") or "Dockerfile" in path:
            result["deploy"] = True
    return result


def main() -> int:
    paths = sys.stdin.read().splitlines()
    for key, value in classify(paths).items():
        print(f"{key}={'true' if value else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
