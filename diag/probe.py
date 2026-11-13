import os, requests
B = os.environ["WP_URL"].rstrip("/")
S = requests.Session(); S.auth = (os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"]); S.headers["User-Agent"] = "GamerQuest-GitHub-Actions/1.0"
u = f"{B}/wp-json/wp/v2/posts/944"
r = S.post(u, json={"status": "not-a-real-status"}, timeout=30)
print("INVALID PARAM", r.status_code, r.text[:200])
r = S.get(f"{B}/wp-json/wp/v2/plugins", params={"status": "active"}, timeout=30)
print("PLUGINS", r.status_code)
if r.ok:
    for p in r.json(): print("  PLUGIN", p.get("plugin"), "|", p.get("name"), p.get("version"))
else: print(r.text[:200])
r = S.get(f"{B}/wp-json/wp/v2/themes", params={"status": "active"}, timeout=30)
print("THEME", r.status_code, [(t.get("stylesheet"), (t.get("version"))) for t in (r.json() if r.ok else [])])
r = S.get(f"{B}/wp-json/wp/v2/users/me", params={"context": "edit"}, timeout=30)
print("ME", r.status_code, (r.json() if r.ok else {}).get("roles"))
r = S.get(f"{B}/wp-json/wp/v2/posts", params={"per_page": 1, "orderby": "modified", "_fields": "id,modified,date"}, timeout=30)
print("LAST MODIFIED POST", r.json())
