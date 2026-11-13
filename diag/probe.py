import os, requests, json
B = os.environ["WP_URL"].rstrip("/")
S = requests.Session(); S.auth = (os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"]); S.headers["User-Agent"] = "GamerQuest-GitHub-Actions/1.0"
for path in ["functions.php", "wp-content/themes/gamerquest-fr-v2/functions.php", "themes/gamerquest-fr-v2/functions.php"]:
    r = S.post(f"{B}/wp-json/wpvibe/v1/file/read", json={"path": path, "start_line": 420, "end_line": 500}, timeout=60)
    print("READ", path, r.status_code)
    try: d = r.json(); print(json.dumps({k: v for k, v in d.items() if k != "content"}, ensure_ascii=False)[:400]); print(d.get("content", "")[:6000])
    except Exception: print(r.text[:500])
r = S.get(f"{B}/wp-json/wpvibe/v1/draft-theme/preview", timeout=60); print("DRAFT PREVIEW", r.status_code, r.text[:500])
r = S.get(f"{B}/wp-json/wpvibe/v1/audit-log", params={"limit": 15}, timeout=60); print("AUDIT", r.status_code, r.text[:3000])
