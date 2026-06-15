import respx
import httpx
import pytest

from tools.feishu_bitable import fetch_token, read_bitable_records


@respx.mock
def test_fetch_token_returns_tenant_access_token():
    respx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    ).mock(return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200}))

    token = fetch_token("cli_x", "secret_x")
    assert token == "t-abc"


@respx.mock
def test_fetch_token_raises_on_error_code():
    respx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    ).mock(return_value=httpx.Response(200, json={"code": 99991663, "msg": "app not found"}))

    with pytest.raises(RuntimeError, match="飞书鉴权失败"):
        fetch_token("bad", "bad")


@respx.mock
def test_read_bitable_records_returns_columns_and_rows():
    respx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    ).mock(return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200}))
    respx.get(
        "https://open.feishu.cn/open-apis/bitable/v1/apps/APP/tables/TBL/records"
    ).mock(return_value=httpx.Response(200, json={
        "code": 0,
        "data": {
            "has_more": False,
            "items": [
                {"fields": {"标题": "露营好物", "点赞": 1200, "正文": "正文内容"}},
                {"fields": {"标题": "帐篷测评", "点赞": 980, "正文": "另一篇"}},
            ],
        },
    }))

    result = read_bitable_records("cli_x", "secret_x", "APP", "TBL")
    assert set(result["columns"]) == {"标题", "点赞", "正文"}
    assert len(result["rows"]) == 2
    assert result["rows"][0]["标题"] == "露营好物"


@respx.mock
def test_read_bitable_records_paginates_across_pages():
    respx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    ).mock(return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200}))

    route = respx.get(
        "https://open.feishu.cn/open-apis/bitable/v1/apps/APP/tables/TBL/records"
    )
    route.side_effect = [
        httpx.Response(200, json={
            "code": 0,
            "data": {
                "has_more": True,
                "page_token": "pg2",
                "items": [{"fields": {"标题": "第一页"}}],
            },
        }),
        httpx.Response(200, json={
            "code": 0,
            "data": {
                "has_more": False,
                "items": [{"fields": {"标题": "第二页"}}],
            },
        }),
    ]

    result = read_bitable_records("cli_x", "secret_x", "APP", "TBL")
    assert len(result["rows"]) == 2
    assert result["rows"][0]["标题"] == "第一页"
    assert result["rows"][1]["标题"] == "第二页"
    assert route.call_count == 2
