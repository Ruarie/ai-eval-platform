#!/usr/bin/env python3
"""Alembic 迁移链检查：必须恰好一个 head。

背景：两条 PR 各自把迁移接在同一个父节点上，就会在 main 上形成多个 head，
CI 的迁移作业直接失败（`Multiple head revisions are present`），部署被跳过。
这类问题在合并前就能查出来，不该等到部署阶段。

只用标准库解析迁移文件里的 `revision` / `down_revision`，不连数据库、不装依赖。

用法：
    python3 tools/check_migration_heads.py            # 默认检查 backend/api/migrations/versions
    python3 tools/check_migration_heads.py <目录>      # 指定其他目录（测试用）

退出码：0 = 恰好一个 head；1 = 0 个或多个 head。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "backend/api/migrations/versions"


def _literal(node: ast.AST):
    """把 AST 节点还原成字符串或字符串元组；无法静态求值返回 None。"""
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _assignments(tree: ast.Module) -> dict[str, object]:
    """收集模块级的 revision / down_revision 赋值（含 Annotated 赋值）。"""
    found: dict[str, object] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            targets = [node.targets[0]]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                literal = _literal(value)
                if literal is not None:
                    found[target.id] = literal
    return found


def collect(directory: Path) -> tuple[dict[str, str], set[str]]:
    """返回 ({revision: 文件名}, 被引用为父节点的 revision 集合)。"""
    revisions: dict[str, str] = {}
    parents: set[str] = set()
    for path in sorted(directory.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # 语法错的迁移文件本身就该拦下
            raise SystemExit(f"错误：{path.name} 无法解析：{exc}") from exc
        values = _assignments(tree)
        revision = values.get("revision")
        if not isinstance(revision, str):
            # 不是迁移文件（例如 __init__.py）就跳过。
            continue
        if revision in revisions:
            raise SystemExit(f"错误：revision {revision} 重复定义：{revisions[revision]} 与 {path.name}")
        revisions[revision] = path.name
        down = values.get("down_revision")
        if isinstance(down, str):
            parents.add(down)
        elif isinstance(down, (tuple, list)):
            parents.update(item for item in down if isinstance(item, str))
    return revisions, parents


def main(argv: list[str]) -> int:
    directory = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_DIR
    if not directory.is_dir():
        print(f"错误：迁移目录不存在：{directory}", file=sys.stderr)
        return 1

    revisions, parents = collect(directory)
    heads = [rev for rev in revisions if rev not in parents]

    if len(heads) == 1:
        print(f"OK：迁移链唯一 head {heads[0]}（{revisions[heads[0]]}，共 {len(revisions)} 个迁移）")
        return 0

    if not heads:
        print(f"错误：未找到任何 head（{len(revisions)} 个迁移全是别人的父节点？）", file=sys.stderr)
        return 1

    print(f"错误：发现 {len(heads)} 个 head，合并后会导致迁移作业失败：", file=sys.stderr)
    for rev in heads:
        print(f"  - {rev}  ({revisions[rev]})", file=sys.stderr)
    print(
        "\n修法：把其中一条迁移的 down_revision 指向另一条的 revision，"
        "或新增一条 merge 迁移（down_revision 用元组同时指向两个 head）。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
