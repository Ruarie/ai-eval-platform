#!/usr/bin/env python3
"""上游直连诊断：绕过平台，用同一套 prompt 直连模型，定位「JSON 解析失败」的真实原因。

它回答三个问题：
1. 模型是否把输出预算花在了 reasoning_content 上（finish_reason=length 但 content 为空/截断）；
2. 同一需求重复调用时失败率有多高（平台侧表现为 502「模型输出无法解析为用例」）；
3. 截断发生在第几个字符（是否正好卡在 JSON 数组中间）。

用法：
    python diagnose_upstream.py --fixture order-refund --repeat 3
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.casegen import build_prompts, generation_token_budget, parse_cases  # noqa: E402

from agent_eval.fixtures import by_id  # noqa: E402

PROFILE_ENV = "/run/config/.env"


def read_env(container: str) -> dict[str, str]:
    raw = subprocess.run(
        ["docker", "exec", container, "cat", PROFILE_ENV],
        capture_output=True, text=True, timeout=20,
    ).stdout
    values = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="ai-eval-platform-api-1")
    parser.add_argument("--profile-id", default="ab40b157-6d0d-4fd5-a147-0bd60e8b1945")
    parser.add_argument("--fixture", default="order-refund")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--max-count", type=int, default=0)
    args = parser.parse_args()

    env = read_env(args.container)
    token = re.sub(r"[^A-Za-z0-9]+", "_", args.profile_id).strip("_").upper()
    base = env.get(f"AI_PROFILE_{token}_BASE_URL", "").rstrip("/")
    model = env.get(f"AI_PROFILE_{token}_MODEL", "")
    key = env.get(f"AI_PROFILE_{token}_API_KEY", "")
    if not (base and model and key):
        print(f"协议档 {args.profile_id} 缺少连接信息", file=sys.stderr)
        return 2

    fixture = by_id(args.fixture)
    count = args.max_count or fixture["max_count"]
    system, user = build_prompts(fixture["text"], count)
    budget = generation_token_budget(count)
    print(f"fixture={fixture['id']} max_count={count} max_tokens={budget} model={model}")

    rows = []
    for index in range(args.repeat):
        response = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0.3,
                "max_tokens": budget,
            },
            timeout=300,
        )
        data = response.json()
        message = (data.get("choices") or [{}])[0].get("message") or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        finish = (data.get("choices") or [{}])[0].get("finish_reason")
        try:
            parsed = parse_cases(content)
            ok, detail = True, f"{len(parsed)} 条"
        except Exception as exc:  # noqa: BLE001 - 诊断脚本需要保留原始异常
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        rows.append({
            "run": index + 1,
            "http": response.status_code,
            "finish": finish,
            "content_chars": len(content),
            "reasoning_chars": len(reasoning),
            "parse_ok": ok,
            "detail": detail,
            "tail": content[-60:].replace("\n", " "),
            "usage": data.get("usage"),
        })
        print(json.dumps(rows[-1], ensure_ascii=False))

    fails = sum(1 for row in rows if not row["parse_ok"])
    print(f"\n解析失败 {fails}/{len(rows)}；finish_reason=length 的占比 "
          f"{sum(1 for row in rows if row['finish'] == 'length')}/{len(rows)}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
