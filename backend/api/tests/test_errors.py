"""错误码枚举单测（M0 空跑，不依赖数据库）。"""

from app.errors import _CODE_STATUS, ErrorCode


def test_error_code_enum_matches_contract():
    # PRD 5.5 / API V1.0 §1.3 基础十码 + F5/G6 的 DENIED + 登录限流的 RATE_LIMITED
    expected = {
        "UNAUTHORIZED",
        "VALIDATION",
        "NOT_FOUND",
        "BUDGET_EXCEEDED",
        "CONCURRENCY",
        "WHITELIST",
        "NEED_APPROVAL",
        "UPSTREAM",
        "TIMEOUT",
        "INTERNAL",
        "DENIED",
        "RATE_LIMITED",
    }
    assert {c.value for c in ErrorCode} == expected


def test_error_code_default_status_mapping():
    assert _CODE_STATUS[ErrorCode.UNAUTHORIZED] == 403
    assert _CODE_STATUS[ErrorCode.VALIDATION] == 400
    assert _CODE_STATUS[ErrorCode.NOT_FOUND] == 404
    assert _CODE_STATUS[ErrorCode.BUDGET_EXCEEDED] == 409
    assert _CODE_STATUS[ErrorCode.CONCURRENCY] == 409
    assert _CODE_STATUS[ErrorCode.WHITELIST] == 403
    assert _CODE_STATUS[ErrorCode.NEED_APPROVAL] == 403
    assert _CODE_STATUS[ErrorCode.UPSTREAM] == 502
    assert _CODE_STATUS[ErrorCode.TIMEOUT] == 504
    assert _CODE_STATUS[ErrorCode.INTERNAL] == 500
    assert _CODE_STATUS[ErrorCode.DENIED] == 403  # F5/G6：只读拒写（授权语义）
    assert _CODE_STATUS[ErrorCode.RATE_LIMITED] == 429  # 登录失败限流


def test_unknown_route_returns_unified_error_body(client):
    """路由不存在也必须返回 {code,message}，前端无需为 404 单独分支。"""
    resp = client.get("/api/definitely-not-a-route")
    assert resp.status_code == 404
    assert resp.json() == {"code": "NOT_FOUND", "message": "接口不存在"}
