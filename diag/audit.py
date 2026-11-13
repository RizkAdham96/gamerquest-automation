import os, re, requests
from requests.auth import HTTPBasicAuth
B = os.environ.get("WP_URL", "https://gamerquestfr.com").rstrip("/")
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 GamerQuest-Audit"
A = HTTPBasicAuth(os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"])
posts = []
for page in (1, 2, 3):
    r = S.get(f"{B}/wp-json/wp/v2/posts", params={"per_page": 100, "page": page, "_fields": "id,slug,date,featured_media,link,categories,content"}, auth=A, timeout=60)
    if r.status_code != 200: break
    posts += r.json()
print("TOTAL_POSTS", len(posts))
no_fm = [p for p in posts if not p.get("featured_media")]
print("NO_FEATURED_MEDIA", len(no_fm))
for p in no_fm[:80]: print("  NOFM", p["date"][:10], p["id"], p["slug"][:70], p["categories"])
ids = sorted({p["featured_media"] for p in posts if p.get("featured_media")})
media = {}
for i in range(0, len(ids), 100):
    r = S.get(f"{B}/wp-json/wp/v2/media", params={"include": ",".join(map(str, ids[i:i+100])), "per_page": 100, "_fields": "id,source_url,mime_type,media_details"}, auth=A, timeout=60)
    for m in r.json(): media[m["id"]] = m
print("MEDIA_FOUND", len(media), "of", len(ids))
nosizes = 0
for p in posts[:60]:
    m = media.get(p.get("featured_media"))
    if not m: 
        if p.get("featured_media"): print("  MISSINGMEDIA", p["id"], p["slug"][:60], p["featured_media"])
        continue
    sizes = (m.get("media_details") or {}).get("sizes") or {}
    if len(sizes) <= 1: nosizes += 1
    print("  M", p["date"][:10], p["slug"][:50], "|", m.get("mime_type"), "| sizes:", ",".join(sorted(sizes))[:80], "|", m.get("source_url", "")[-60:])
print("NO_THUMB_SIZES_IN_60", nosizes)
noimg_body = sum(1 for p in posts if "<img" not in (p.get("content") or {}).get("rendered", ""))
print("POSTS_WITHOUT_IMG_IN_BODY", noimg_body, "of", len(posts))
for path in ("/", "/page/2/", "/category/actualites/"):
    r = S.get(B + path, timeout=60); h = r.text
    arts = re.findall(r"<article\b.*?</article>", h, re.S)
    if not arts: arts = re.findall(r'<(?:div|li)[^>]*class="[^"]*(?:post|card|entry)[^"]*"[^>]*>.*?</(?:div|li)>', h, re.S)
    print("PAGE", path, r.status_code, "articles:", len(arts), "without_img:", sum(1 for a in arts if "<img" not in a))
    for a in arts:
        if "<img" not in a:
            t = re.search(r'href="([^"]+)"', a); print("   NOIMG", t.group(1) if t else a[:120])
    imgs = re.findall(r'<img[^>]+>', h)
    print("   sample imgs:", [re.sub(r"\s+", " ", x)[:220] for x in imgs[:6]])
