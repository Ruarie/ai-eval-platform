"""迁移链守卫：恰好一个 head。

背景：两条 PR 各自把迁移接在同一个父节点上，会在 main 形成多个 head，
CI 的迁移作业失败、部署被跳过。这组用例锁定脚本的判定，避免守卫本身失效。
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_migration_heads", ROOT / "tools/check_migration_heads.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class MigrationHeadsTest(unittest.TestCase):
    """每个用例在临时目录里造一份最小迁移集，不碰真实迁移。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="migrations-")
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def write(self, name: str, revision: str, down) -> None:
        """按 alembic 的写法落一个迁移文件；down 支持字符串或元组。"""
        down_literal = repr(down)
        (self.dir / name).write_text(
            f'revision = "{revision}"\n'
            f"down_revision = {down_literal}\n"
            f"branch_labels = None\n"
            f"depends_on = None\n",
            encoding="utf-8",
        )

    def test_single_head_passes(self) -> None:
        self.write("a.py", "a1", None)
        self.write("b.py", "b1", "a1")
        self.assertEqual(CHECKER.main(["check", str(self.dir)]), 0)

    def test_two_heads_fail(self) -> None:
        self.write("a.py", "a1", None)
        self.write("b.py", "b1", "a1")
        self.write("c.py", "c1", "a1")
        self.assertEqual(CHECKER.main(["check", str(self.dir)]), 1)

    def test_merge_revision_joins_two_heads(self) -> None:
        self.write("a.py", "a1", None)
        self.write("b.py", "b1", None)
        self.write("merge.py", "m1", ("a1", "b1"))
        self.write("c.py", "c1", "m1")
        self.assertEqual(CHECKER.main(["check", str(self.dir)]), 0)

    def test_duplicate_revision_is_rejected(self) -> None:
        self.write("a.py", "same", None)
        self.write("b.py", "same", None)
        with self.assertRaises(SystemExit):
            CHECKER.main(["check", str(self.dir)])

    def test_missing_directory_is_rejected(self) -> None:
        self.assertEqual(CHECKER.main(["check", str(self.dir / "nope")]), 1)


if __name__ == "__main__":
    unittest.main()
