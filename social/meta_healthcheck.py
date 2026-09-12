import os


def _clean(value):
    return "" if value is None else str(value).strip()


def _require(value, name):
    value = _clean(value)
    if not value:
        raise RuntimeError(f"Missing required Meta value: {name}")
    return value


def _requests(requests_module=None):
    if requests_module is not None:
        return requests_module
    import requests
    return requests


def _check_one(requests_module, base_url, object_id, token, label):
    response = requests_module.get(
        f"{base_url}/{object_id}",
        params={"fields": "id", "access_token": token},
        timeout=30,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if getattr(response, "status_code", 0) >= 400 or "error" in payload:
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = _clean(error.get("message")) if isinstance(error, dict) else ""
        code = _clean(error.get("code")) if isinstance(error, dict) else ""
        details = f" message: {message}" if message else ""
        if code:
            details += f" code: {code}"
        raise RuntimeError(f"Meta {label} health check failed.{details}")
    returned_id = _clean(payload.get("id")) if isinstance(payload, dict) else ""
    if not returned_id:
        raise RuntimeError(f"Meta {label} health check returned no account ID.")
    return returned_id


def check_meta_connection(
    token,
    ig_user_id,
    page_id,
    requests_module=None,
    graph_version="v26.0",
):
    token = _require(token, "access token")
    ig_user_id = _require(ig_user_id, "Instagram user ID")
    page_id = _require(page_id, "Facebook page ID")
    graph_version = _require(graph_version, "Graph API version")
    requests_module = _requests(requests_module)
    base_url = f"https://graph.facebook.com/{graph_version}"
    checked_ig = _check_one(requests_module, base_url, ig_user_id, token, "Instagram")
    checked_page = _check_one(requests_module, base_url, page_id, token, "Facebook Page")
    return {
        "ok": True,
        "instagram_id": checked_ig,
        "page_id": checked_page,
        "graph_version": graph_version,
    }


def main():
    token = os.environ.get("META_FB_PAGE_ACCESS_TOKEN", "")
    ig_user_id = os.environ.get("META_IG_USER_ID", "")
    page_id = os.environ.get("META_PAGE_ID", "")
    graph_version = os.environ.get("META_GRAPH_API_VERSION", "v26.0")
    result = check_meta_connection(
        token=token,
        ig_user_id=ig_user_id,
        page_id=page_id,
        graph_version=graph_version,
    )
    print("Meta preflight health check passed.")
    print(f"Instagram account ID: {result['instagram_id']}")
    print(f"Facebook Page ID: {result['page_id']}")
    print(f"Graph API version: {result['graph_version']}")


if __name__ == "__main__":
    main()
