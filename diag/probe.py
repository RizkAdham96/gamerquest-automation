import os, requests
B = os.environ["WP_URL"].rstrip("/")
S = requests.Session(); S.auth = (os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"]); S.headers["User-Agent"] = "GamerQuest-GitHub-Actions/1.0"
u = f"{B}/wp-json/wp/v2/posts/944"
r = S.get(u, params={"context": "edit"}, timeout=30)
print("GET edit", r.status_code, r.url[-40:], "history", [h.status_code for h in r.history])
j = r.json() if r.ok else {}
for f in ("title", "content", "excerpt"):
    v = (j.get(f) or {}); print(" ", f, "raw len", len(v.get("raw") or ""), "rendered len", len(v.get("rendered") or ""))
print("  status", j.get("status"), "type", j.get("type"), "featured", j.get("featured_media"), "format", j.get("format"))
r = S.post(u, json={"featured_media": j.get("featured_media")}, timeout=30, allow_redirects=False)
print("POST same media (no-op)", r.status_code, r.headers.get("Location"), r.text[:200])
r = S.post(u, json={"featured_media": j.get("featured_media")}, params={"_method": "PUT"}, timeout=30, allow_redirects=False)
print("POST _method=PUT", r.status_code, r.text[:200])
r = S.put(u, json={"featured_media": j.get("featured_media")}, timeout=30, allow_redirects=False)
print("PUT", r.status_code, r.text[:200])
r = S.post(u, data={"featured_media": j.get("featured_media")}, timeout=30, allow_redirects=False)
print("POST form", r.status_code, r.text[:200])
r = S.post(f"{B}/?rest_route=/wp/v2/posts/944", json={"featured_media": j.get("featured_media")}, timeout=30, allow_redirects=False)
print("POST rest_route", r.status_code, r.text[:200])
