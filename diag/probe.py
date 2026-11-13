import os, requests
B = os.environ["WP_URL"].rstrip("/")
S = requests.Session(); S.auth = (os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"]); S.headers["User-Agent"] = "GamerQuest-GitHub-Actions/1.0"
j = S.get(f"{B}/wp-json/", timeout=60).json()
print("NAMESPACES", j.get("namespaces"))
for route, info in j.get("routes", {}).items():
    if "gamerquest" in route or "gq" in route.split("/")[1:2] or "vibe" in route:
        print("ROUTE", route, [e.get("methods") for e in info.get("endpoints", [])], list((info.get("endpoints") or [{}])[0].get("args", {}).keys())[:12])
m = S.get(f"{B}/wp-json/wp/v2/posts/944", params={"context": "edit", "_fields": "meta"}, timeout=30).json()
print("META944", str(m)[:600])
