"""临时改写协议档环境文件，把 Agent 指向本地假模型。

两种落地方式：
- `ProfileEnvPatch`：直接改宿主机 `.env`（进程内直接读文件的服务适用）；
- `DockerEnvPatch`：改容器内看到的 `/run/config/.env`。

为什么需要后者：Docker 单文件 bind mount 固定的是启动时的 inode。若部署脚本用
「写新文件再 rename」方式更新 `.env`，容器内仍持有旧 inode，宿主机改动对运行中
服务不可见。此时只能改容器内那份文件，或重启容器。

两种方式都做**原地追加 + 逐字节还原**，避免换 inode 或残留测试配置。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_TOKEN = re.compile(r"[^A-Za-z0-9]+")


def profile_env_keys(profile_id: str) -> dict[str, str]:
    token = _TOKEN.sub("_", profile_id).strip("_").upper() or "UNKNOWN"
    return {
        "base_url": f"AI_PROFILE_{token}_BASE_URL",
        "model": f"AI_PROFILE_{token}_MODEL",
        "api_key": f"AI_PROFILE_{token}_API_KEY",
    }


def _override_block(profile_id: str, *, base_url: str, model: str, api_key: str) -> bytes:
    keys = profile_env_keys(profile_id)
    lines = ["\n# === agent-eval stub override (auto restored) ==="]
    lines += [f"{keys['base_url']}={base_url}", f"{keys['model']}={model}", f"{keys['api_key']}={api_key}"]
    return ("\n".join(lines) + "\n").encode("utf-8")


class ProfileEnvPatch:
    """宿主机 `.env` 原地追加 / 还原。"""

    def __init__(self, env_path: str | Path, profile_id: str, *, base_url: str, model: str, api_key: str) -> None:
        self.path = Path(env_path)
        self.block = _override_block(profile_id, base_url=base_url, model=model, api_key=api_key)
        self.original: bytes | None = None

    def __enter__(self) -> ProfileEnvPatch:
        self.original = self.path.read_bytes()
        with self.path.open("ab") as handle:
            handle.write(self.block)
        return self

    def __exit__(self, *exc: object) -> None:
        assert self.original is not None
        with self.path.open("r+b") as handle:
            handle.seek(0)
            handle.write(self.original)
            handle.truncate()


class DockerEnvPatch:
    """容器内 `/run/config/.env` 原地追加 / 还原（api 容器可写，worker 只读）。"""

    def __init__(
        self,
        container: str,
        profile_id: str,
        *,
        base_url: str,
        model: str,
        api_key: str,
        env_path: str = "/run/config/.env",
    ) -> None:
        self.container = container
        self.env_path = env_path
        self.block = _override_block(profile_id, base_url=base_url, model=model, api_key=api_key)
        self.original: bytes | None = None

    def _exec(self, args: list[str], *, stdin: bytes | None = None, check: bool = True) -> bytes:
        result = subprocess.run(
            ["docker", "exec", "-i", self.container, *args],
            input=stdin,
            capture_output=True,
            timeout=30,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"docker exec 失败：{result.stderr.decode('utf-8', 'ignore')[:200]}")
        return result.stdout

    def __enter__(self) -> DockerEnvPatch:
        self.original = self._exec(["cat", self.env_path])
        self._exec(["sh", "-c", f"cat >> {self.env_path}"], stdin=self.block)
        return self

    def __exit__(self, *exc: object) -> None:
        assert self.original is not None
        self._exec(["sh", "-c", f"cat > {self.env_path}"], stdin=self.original)
