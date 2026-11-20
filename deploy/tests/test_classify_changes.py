"""PR 阶段的作业分流：改了哪块就跑哪块，避免改前端也跑 96 秒的后端。

分类错一次的代价是「该跑的没跑」，所以边界要逐条钉住：
迁移必须连带后端（迁移要跑同一套 pytest），Dockerfile 归部署脚本作业。
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("classify_changes", ROOT / "deploy/classify_changes.py")
CLASSIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLASSIFIER)


class ClassifyChangesTest(unittest.TestCase):
    def test_backend_only(self) -> None:
        got = CLASSIFIER.classify(["backend/api/app/routers/cases.py"])
        self.assertEqual(got, {"backend": True, "frontend": False, "deploy": False, "migrations": False})

    def test_frontend_only(self) -> None:
        got = CLASSIFIER.classify(["frontend/src/views/Cases.vue"])
        self.assertEqual(got, {"backend": False, "frontend": True, "deploy": False, "migrations": False})

    def test_migration_also_runs_backend(self) -> None:
        """迁移改了后端就必须跟着验，否则迁移与代码不同步。"""
        got = CLASSIFIER.classify(["backend/api/migrations/versions/c4d8e2a1f6b3_用例集软删除.py"])
        self.assertTrue(got["migrations"])
        self.assertTrue(got["backend"])
        self.assertFalse(got["frontend"])

    def test_deploy_surface(self) -> None:
        for path in ["deploy/deploy.sh", "docker-compose.yml", "docker/api.Dockerfile"]:
            got = CLASSIFIER.classify([path])
            self.assertTrue(got["deploy"], path)
            self.assertFalse(got["backend"], path)

    def test_ci_config_runs_everything(self) -> None:
        got = CLASSIFIER.classify([".github/workflows/ci.yml"])
        self.assertTrue(all(got.values()))

    def test_docs_or_tools_change_nothing(self) -> None:
        """纯文档、守卫脚本以外的工具改动不该消耗 Runner。"""
        got = CLASSIFIER.classify(["docs/API.md", "README.md", "tools/seed_demo_users.py"])
        self.assertEqual(got, {"backend": False, "frontend": False, "deploy": False, "migrations": False})

    def test_mixed_changes_union(self) -> None:
        got = CLASSIFIER.classify(["backend/shared/models.py", "frontend/src/api/http.ts"])
        self.assertTrue(got["backend"])
        self.assertTrue(got["frontend"])
        self.assertFalse(got["migrations"])


if __name__ == "__main__":
    unittest.main()
