"""编排一致性守卫：删服务时要连引用一起删。

`docker compose` 遇到悬空的 `depends_on` 会直接判定整个项目非法
（``service "worker" depends on undefined service "stress"``），
而这种错误只有在部署机执行 `docker compose config` 时才暴露。
本测试在 CI 阶段就把这类引用问题拦下来。

PyYAML 不可用时跳过，不阻塞流水线。
"""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 仅缺少可选依赖时走到
    yaml = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"


@unittest.skipIf(yaml is None, "PyYAML 未安装，跳过编排一致性检查")
class ComposeConsistencyTest(unittest.TestCase):
    """只做静态引用检查，不启动任何容器。"""

    def setUp(self) -> None:
        self.config = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        self.services = self.config.get("services", {})

    def test_depends_on_targets_exist(self) -> None:
        """每个 depends_on 目标都必须是已定义的服务。"""
        dangling: list[str] = []
        for name, spec in self.services.items():
            depends = spec.get("depends_on") or {}
            targets = depends if isinstance(depends, dict) else {item: {} for item in depends}
            for target in targets:
                if target not in self.services:
                    dangling.append(f"{name} -> {target}")
        self.assertEqual(dangling, [], f"存在悬空依赖：{dangling}")

    def test_retired_stress_service_not_referenced(self) -> None:
        """压测引擎已下线：服务、依赖与镜像跟踪都不应再指向它。"""
        self.assertNotIn("stress", self.services, "stress 服务应保持下线")
        for name, spec in self.services.items():
            depends = spec.get("depends_on") or {}
            targets = depends if isinstance(depends, dict) else dict.fromkeys(depends)
            self.assertNotIn("stress", targets, f"{name} 仍依赖已下线的 stress")

        deploy_sh = (ROOT / "deploy/deploy.sh").read_text(encoding="utf-8")
        tracked = next(
            (line for line in deploy_sh.splitlines() if line.startswith("TRACKED_IMAGE_SERVICES=")),
            "",
        )
        self.assertNotIn(" stress", tracked, "deploy.sh 的镜像跟踪列表仍包含 stress")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
