import os, requests, json
B = os.environ["WP_URL"].rstrip("/")
S = requests.Session(); S.auth = (os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"]); S.headers["User-Agent"] = "GamerQuest-GitHub-Actions/1.0"
for pat in ["wp_insert_post_empty_content", "rest_pre_insert_post", "empty_content", "rest_pre_dispatch", "featured_media"]:
    r = S.post(f"{B}/wp-json/wpvibe/v1/file/search", json={"pattern": pat, "extensions": ["php"], "max_results": 40}, timeout=60)
    print("SEARCH", pat, r.status_code)
    txt = r.text
    try:
        d = r.json(); items = d.get("results") or d.get("matches") or d
        for it in (items if isinstance(items, list) else [items])[:40]:
            s = json.dumps(it, ensure_ascii=False)
            if "wp-includes" in s or "wp-admin" in s or "google-site-kit" in s: continue
            print("  ", s[:300])
    except Exception:
        print("  ", txt[:400])
