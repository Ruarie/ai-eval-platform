#!/usr/bin/env python3
"""Agent 自动化全量测试入口。

用法示例：
    # 全部离线可跑套件（本地假模型，不烧真实额度）
    python run.py --user admin --password admin123 --suites env,gen,case,task

    # 真实模型下的用例质量评测（需已配置 Agent 协议档）
    python run.py --suites env,quality

套件说明：
    env    健康检查、鉴权、错误契约、专家与协议档可用性
    gen    AI 候选生成链路（正常/异常/超配额/去重/参数校验/prompt 契约/覆盖/补全）
    case   用例集生命周期（候选入库、版本冲突、确认、已确认不可改、废弃）
    task   用例任务端到端（入队 → Worker → 草稿 → 确认 → succeeded）
    quality 真实模型质量评测（规则评分七维度）
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_eval.core import Api, CheckFailed, Recorder  # noqa: E402
from agent_eval.envfile import DockerEnvPatch, ProfileEnvPatch  # noqa: E402
from agent_eval.report import render_markdown  # noqa: E402
from agent_eval.stub_model import StubModel  # noqa: E402
from agent_eval.suites import run_env, run_generation, run_lifecycle, run_task_e2e  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def discover_container(container_hint: str = "api") -> str | None:
    try:
        listing = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=8
        )
        names = [name for name in listing.stdout.split() if container_hint in name]
        return names[0] if names else None
    except (OSError, subprocess.SubprocessError):
        return None


def discover_gateway(container_hint: str = "api") -> str | None:
    """取 API 容器所在网络的网关地址，即容器内可达的宿主机 IP。"""
    try:
        listing = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=8
        )
        names = [name for name in listing.stdout.split() if container_hint in name]
        if not names:
            return None
        info = subprocess.run(
            ["docker", "inspect", names[0], "-f",
             "{{range .NetworkSettings.Networks}}{{.Gateway}} {{end}}"],
            capture_output=True, text=True, timeout=8,
        )
        ips = [ip for ip in info.stdout.split() if ip and ip != "<no value>"]
        return ips[0] if ips else None
    except (OSError, subprocess.SubprocessError):
        return None


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def resolve_profile(api: Api) -> dict[str, Any] | None:
    """优先取系统设置里的 agent_profile_id（唯一事实源），退回能力列表首项。"""
    settings = api.get("/api/admin/settings").body
    if isinstance(settings, dict) and settings.get("agent_profile_id"):
        return {"id": settings["agent_profile_id"]}
    body = api.get("/api/sessions/agent-ui").body
    if not isinstance(body, dict):
        return None
    profiles = body.get("profiles") or []
    return profiles[0] if profiles else None


def write_reports(
    out_dir: Path,
    checks: list,
    *,
    meta: dict[str, Any],
    quality: list[dict[str, Any]],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(
            {
                "meta": meta,
                "checks": [check.__dict__ for check in checks],
                "quality": quality,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_path = out_dir / "report.md"
    report_path.write_text(render_markdown(checks, meta=meta, quality=quality), encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="ai-eval-platform Agent 全量测试")
    parser.add_argument("--base", default=os.environ.get("AE_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--user", default=os.environ.get("AE_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("AE_PASSWORD", ""))
    parser.add_argument("--suites", default="env,gen,case,task")
    parser.add_argument("--env-file", default=str(ROOT / ".env"), help="协议档环境文件（stub 模式临时改写）")
    parser.add_argument("--profile-id", default="", help="默认取 agent-ui 暴露的第一个协议档")
    parser.add_argument("--stub-host", default="", help="容器可达的宿主机地址，默认自动探测 docker 网关")
    parser.add_argument("--env-container", default="auto",
                        help="改写哪个容器内的 /run/config/.env；auto=自动探测 api 容器，none=改宿主机 .env")
    parser.add_argument("--stub-port", type=int, default=18080)
    parser.add_argument("--report-dir", default=str(Path(__file__).parent / "reports"))
    parser.add_argument("--json", action="store_true", help="同时打印机器可读结果")
    args = parser.parse_args()

    suites = [item.strip() for item in args.suites.split(",") if item.strip()]
    password = args.password or os.environ.get("AE_PASSWORD", "")
    if not password:
        print("缺少登录密码：--password 或 AE_PASSWORD", file=sys.stderr)
        return 2

    api = Api(args.base)
    try:
        api.login(args.user, password)
    except CheckFailed as exc:
        print(f"登录失败：{exc}", file=sys.stderr)
        return 2

    health = api.get("/api/health").body or {}
    needs_stub = any(name in suites for name in ("gen", "case", "task"))
    meta: dict[str, Any] = {
        "base": args.base,
        "user": args.user,
        "commit": health.get("commit"),
        "version": health.get("version"),
        "model_mode": (
            "混合：gen/case 走本地假模型，task/quality 走真实模型"
            if "quality" in suites and needs_stub
            else "live(真实模型)" if "quality" in suites
            else "stub(本地假模型)"
        ),
        "notes": [],
        "suites": suites,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    rec = Recorder()
    quality_reports: list[dict[str, Any]] = []

    stub: StubModel | None = None
    patch: ProfileEnvPatch | None = None

    def setup_stub() -> None:
        """把 Agent 指向本地假模型；必须在 env 套件之后执行，否则会掩盖真实可用性。"""
        nonlocal stub, patch
        profile = resolve_profile(api)
        profile_id = args.profile_id or (profile or {}).get("id")
        if not profile_id:
            raise CheckFailed("未找到 Agent 协议档，无法进行 stub 模式测试")
        host = args.stub_host or discover_gateway() or local_ip()
        stub = StubModel(host="0.0.0.0", port=args.stub_port).start()
        stub_base = f"http://{host}:{args.stub_port}/v1"
        container = None if args.env_container == "none" else (
            args.env_container if args.env_container != "auto" else discover_container()
        )
        if container:
            patch = DockerEnvPatch(container, profile_id, base_url=stub_base,
                                   model="stub-model", api_key="stub-key").__enter__()
            target = f"{container}:/run/config/.env"
        else:
            patch = ProfileEnvPatch(args.env_file, profile_id, base_url=stub_base,
                                    model="stub-model", api_key="stub-key").__enter__()
            target = args.env_file
        meta["notes"].append(
            f"stub 模式：临时把协议档 {profile_id} 指向 {stub_base}（写入 {target}），退出后自动还原"
        )
        meta["stub_host"] = host

    started = time.perf_counter()

    def restore() -> None:
        nonlocal patch, stub
        if patch is not None:
            patch.__exit__(None, None, None)
            patch = None
        if stub is not None:
            stub.stop()
            stub = None

    try:
        if "env" in suites:
            run_env(rec, api)
        if needs_stub:
            setup_stub()
        if "gen" in suites and stub is not None:
            run_generation(rec, api, stub)
        if "case" in suites:
            run_lifecycle(rec, api)
        if "task" in suites and stub is not None:
            run_task_e2e(rec, api)
        # 质量评测必须打真实模型：先还原 stub 配置，避免把假模型输出当成质量结论。
        restore()
        if "quality" in suites:
            from agent_eval.quality import run_quality

            def collect(report: Any) -> None:
                quality_reports.append(report.as_dict())
                print(f"  · {report.fixture_id}: {report.score:.1f} 分 / {report.grade}")

            run_quality(rec, api, on_report=collect)
    except CheckFailed as exc:
        print(f"stub 初始化失败：{exc}", file=sys.stderr)
        restore()
        return 2
    finally:
        restore()

    meta["duration_s"] = round(time.perf_counter() - started, 1)
    out_dir = Path(args.report_dir) / time.strftime("%Y%m%d-%H%M%S")
    report_path = write_reports(out_dir, rec.checks, meta=meta, quality=quality_reports)

    counts = rec.counts()
    print()
    print(f"结果：{counts['pass']} 通过 / {counts['fail']} 失败 / {counts['error']} 异常 / {counts['skip']} 跳过")
    for check in rec.checks:
        if check.status in {"fail", "error"}:
            print(f"  [{check.severity}] {check.suite}/{check.name}: {check.detail[:160]}")
    print(f"报告：{report_path}")

    if args.json:
        print(json.dumps({"counts": counts, "report": str(report_path)}, ensure_ascii=False))
    return 0 if counts["fail"] == 0 and counts["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
