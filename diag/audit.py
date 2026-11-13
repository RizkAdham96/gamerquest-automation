import os, re, requests
B = os.environ.get("WP_URL", "https://gamerquestfr.com").rstrip("/")
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36"
bad = {}
def check(u):
    if u in bad: return bad[u]
    try:
        r = S.get(u, timeout=30, stream=True); ok = r.status_code == 200 and "image" in r.headers.get("Content-Type", ""); r.close()
        bad[u] = None if ok else f"{r.status_code} {r.headers.get('Content-Type')}"
    except Exception as e: bad[u] = str(e)[:80]
    return bad[u]
for path in ("/", "/category/actualites/", "/category/bons-plans/", "/category/guides/"):
    r = S.get(B + path, timeout=60); print("PAGE", path, r.status_code)
    for tag in re.findall(r"<img[^>]+>", r.text):
        src = re.search(r'\bsrc="([^"]+)"', tag); src = src.group(1) if src else ""
        lazy = re.search(r'data-(?:lazy-)?src="([^"]+)"', tag)
        if src.startswith("data:") or not src:
            print("   PLACEHOLDER src, lazy=", lazy.group(1) if lazy else None, tag[:160]); continue
        p = check(src if src.startswith("http") else B + src)
        if p: print("   BROKEN", p, src)
    print("   imgs", len(re.findall(r"<img", r.text)))
posts = S.get(f"{B}/wp-json/wp/v2/posts", params={"per_page": 12, "_fields": "link,slug"}, timeout=60).json()
for p in posts:
    h = S.get(p["link"], timeout=60).text
    main = re.search(r"<main\b.*?</main>", h, re.S); main = main.group(0) if main else h
    imgs = re.findall(r"<img[^>]+>", main)
    real = [i for i in imgs if "gamerquest-logo" not in i]
    srcs = [re.search(r'\bsrc="([^"]+)"', i).group(1) for i in real if re.search(r'\bsrc="([^"]+)"', i)]
    broken = [s for s in srcs if not s.startswith("data:") and check(s)]
    print("POST", p["slug"][:55], "| imgs in main:", len(real), "| wp-post-image:", "wp-post-image" in main, "| og:image:", bool(re.search(r'og:image"', h)), "| broken:", broken[:2])
    if not real: print("   classes near header:", re.findall(r'class="([^"]*(?:hero|thumb|featured|entry-header|post-header)[^"]*)"', h)[:6])
print("BROKEN_TOTAL", sum(1 for v in bad.values() if v), "of", len(bad))
