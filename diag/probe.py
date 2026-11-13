import os, requests
B = os.environ["WP_URL"].rstrip("/")
S = requests.Session(); S.auth = (os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"]); S.headers["User-Agent"] = "GamerQuest-GitHub-Actions/1.0"
j = S.get(f"{B}/wp-json/", timeout=60).json()
for route, info in j.get("routes", {}).items():
    if route.startswith("/gamerquest") or route.startswith("/wpvibe"):
        eps = info.get("endpoints") or []
        print("ROUTE", route, [(e.get("methods"), sorted((e.get("args") or {}).keys())[:10]) for e in eps])
m = S.get(f"{B}/wp-json/wp/v2/posts/944", params={"context": "edit", "_fields": "meta"}, timeout=30).json()
print("META944", str(m)[:600])
