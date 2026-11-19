"""创建演示用普通成员账号，并把引导账号提升为管理端。

仅在受控环境手工执行：

    docker exec -i ai-eval-platform-api-1 python - < tools/seed_demo_users.py

说明：
- 账号 user001…user010 默认密码 ``123456``，**不满足**平台「至少 8 位且含字母
  和数字」的改密规则（该规则只约束接口改密）。这里按产品方要求直接写入哈希，
  登录可用；后续如需改密，必须使用符合规则的密码。
- 脚本幂等：已存在的用户名跳过；admin 已存在时只校正角色为 admin。
"""

from __future__ import annotations

import os
import sys

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.security import hash_password

DEFAULT_PASSWORD = os.environ.get("DEMO_USER_PASSWORD", "123456")
DEFAULT_COUNT = int(os.environ.get("DEMO_USER_COUNT", "10"))


def main() -> int:
    created: list[str] = []
    skipped: list[str] = []
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.bootstrap_admin_username).first()
        if admin is not None and admin.role != "admin":
            admin.role = "admin"
            db.commit()
            print(f"promoted bootstrap account: {admin.username} -> admin")

        for index in range(1, DEFAULT_COUNT + 1):
            username = f"user{index:03d}"
            if db.query(User).filter(User.username == username).first():
                skipped.append(username)
                continue
            db.add(
                User(
                    username=username,
                    display_name=username,
                    password_hash=hash_password(DEFAULT_PASSWORD),
                    role="member",
                    must_change_password=False,
                )
            )
            created.append(username)
        db.commit()
    finally:
        db.close()

    print(f"created={len(created)} skipped={len(skipped)}")
    if created:
        print("new accounts:", ", ".join(created))
    if skipped:
        print("existing accounts:", ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
